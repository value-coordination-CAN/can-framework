"""Forwarding a query between peered nodes (WP-012 §5).

A query travels hop by hop and comes back as **a path and a confidence**, never as
contents. Each node decides for itself whether to answer and whether to pass it on.

Rules, all enforced here:

- **peering is by relationship**: a node talks only to peers it has deliberately added;
- **requests are signed** by the sending node and verified against the peer's public key,
  so a query cannot be forged in a peer's name;
- **no loops**: a node that is already in the path does not answer or forward again;
- **hops are bounded** by a time-to-live, capped by the node's own limit whatever the
  sender asked for;
- **confidence decays**: it is the product of the trust weights along the path, discounted
  once per hop, so four hops of weak links are correctly worth very little;
- **each hop is rate-limited** per peer, and everything is logged locally.
"""
import base64
import hashlib
import json

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utcnow
from app.value.commitments import answer_query, discovery_rules
from app.value.peer_models import Peer, QueryLog


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign_request(body: dict) -> dict:
    """Sign a peer request with this node's key. Unsigned nodes cannot forward."""
    key = settings.NODE_SIGNING_KEY
    if not key:
        raise RuntimeError("this node has no signing key, so it cannot forward queries: set NODE_SIGNING_KEY")
    sk = SigningKey(_unb64(key))
    return {"body": body, "from_node": settings.NODE_ID,
            "signature": _b64(sk.sign(canonical(body)).signature)}


def verify_request(db: Session, envelope: dict) -> Peer:
    """Check that a request really comes from a peer we know and have not suspended."""
    peer = db.query(Peer).filter(Peer.node_id == envelope.get("from_node")).first()
    if peer is None:
        raise PermissionError(f"{envelope.get('from_node')!r} is not a peer of this node")
    if peer.status != "active":
        raise PermissionError(f"peer {peer.node_id} is {peer.status}")
    try:
        VerifyKey(_unb64(peer.public_key)).verify(canonical(envelope["body"]), _unb64(envelope["signature"]))
    except (BadSignatureError, KeyError, ValueError):
        raise PermissionError("signature does not verify for this peer")
    peer.last_seen_at = utcnow()
    db.commit()
    return peer


_peer_counts: dict[str, int] = {}


def check_peer_rate(peer: Peer) -> None:
    limit = int(peer.max_queries_per_hour or discovery_rules().get("peer_max_queries_per_hour", 240))
    key = f"{peer.node_id}:{utcnow().strftime('%Y%m%d%H')}"
    _peer_counts[key] = _peer_counts.get(key, 0) + 1
    if _peer_counts[key] > limit:
        raise PermissionError(f"peer rate limit reached ({limit} an hour)")


# The client used to call a peer. Tests replace it with an in-process one.
def http_peer_client(peer: Peer, envelope: dict, path: str = "/map/peer/query") -> dict | None:
    if not peer.base_url:
        return None
    timeout = float(discovery_rules().get("peer_timeout_seconds", 3))
    try:
        r = httpx.post(f"{peer.base_url.rstrip('/')}{path}", json=envelope, timeout=timeout)
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


PEER_CLIENT = http_peer_client


def call_peer(db: Session, node_id: str, envelope: dict, path: str) -> dict | None:
    """Hand something to a named peer, if it is one and it is active."""
    peer = db.query(Peer).filter(Peer.node_id == node_id, Peer.status == "active").first()
    if peer is None:
        return None
    return PEER_CLIENT(peer, envelope, path)


def log_query(db: Session, **kwargs) -> None:
    db.add(QueryLog(**kwargs))
    db.commit()


def search(db: Session, *, commitment: str, ttl: int, path: list[str], asked_by: str | None,
           direction: str, peer_node_id: str | None = None) -> dict:
    """Answer locally, then pass the query to peers while the time to live allows.

    Returns paths, not contents: each result says how far away a match is, through which
    nodes, and how much confidence the chain of trust weights supports.
    """
    rules = discovery_rules()
    ttl = max(0, min(int(ttl), int(rules.get("max_degree_limit", 6))))
    decay = float(rules.get("hop_decay", 0.6))
    me = settings.NODE_ID
    results: list[dict] = []

    local = answer_query(db, commitment)
    if local["match"]:
        hops = len(path)  # this node's distance from the asker
        results.append({
            "node_id": me,
            "path": path + [me],
            "degree": hops,
            "confidence": 1.0 if hops == 0 else None,  # filled in by the caller that owns the weights
            "match": True,
        })

    if ttl > 0:
        onward = path + [me]
        for peer in db.query(Peer).filter(Peer.status == "active").all():
            if peer.node_id in onward or not peer.base_url:
                continue  # no loops, and nothing to call
            envelope = sign_request({"commitment": commitment, "ttl": ttl - 1, "path": onward})
            answer = PEER_CLIENT(peer, envelope)
            if not answer:
                continue
            for r in answer.get("results", []):
                # A path legitimately starts here; appearing twice is a loop the far side missed.
                if (r.get("path") or []).count(me) > 1:
                    continue
                hop_conf = float(peer.trust_weight or 0.0)
                prior = r.get("confidence")
                r = dict(r)
                r["confidence"] = round(hop_conf * (prior if prior is not None else 1.0) * decay, 6)
                r["degree"] = len(r.get("path", [])) - len(path) - 1
                results.append(r)

    results.sort(key=lambda r: (-(r.get("confidence") or 0), r.get("degree", 99)))
    log_query(db, direction=direction, peer_node_id=peer_node_id, asked_by=asked_by,
              commitment=commitment, ttl=ttl, path=path,
              matched="yes" if results else "no", results=len(results))
    return {"node_id": me, "results": results}


def seal_confidences(payload: dict) -> dict:
    """Local matches have no hop weight, so they are certain by construction."""
    for r in payload.get("results", []):
        if r.get("confidence") is None:
            r["confidence"] = 1.0
    return payload


def commitment_fingerprint(commitment: str) -> str:
    """A short, non-reversible handle for logs and replies."""
    return hashlib.sha256(commitment.encode()).hexdigest()[:12]
