"""Path proofs: an intermediary cannot invent a match or shorten a degree (WP-012 §5).

Without proofs, a node in the middle can say whatever it likes: *there is a match, and it
is one hop away, through me*. That is how a helpful-looking intermediary turns itself into
a toll gate. A proof makes each claim carry a signature from whoever is entitled to make it.

A proof has two parts:

- a **match attestation**, signed by the node that actually holds a match, over the query
  id, the commitment and its own node id. Nobody else can produce it without that node's
  key, so a match cannot be fabricated at a node you do not control;
- a **chain of hop attestations**, one per node the answer passed through. Each hop signs
  the node it received the answer from and a hash of the inner proof, so the chain cannot
  be cut short: shortening means dropping a link whose hash the next signature commits to.

The origin verifies the chain from the outside in and anchors it on its own peer, whose key
it knows. Everything beyond that is verified structurally: an intermediary can invent extra
nodes if it wishes, but inventing *fewer* hops, or a match it does not hold, is refused.

A node with no signing key cannot prove anything. Its answers still travel; they are simply
marked unproven, and a searcher can ask for proven results only.
"""
import base64
import hashlib
import json

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from app.core.config import settings


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def proof_hash(proof: dict | None) -> str:
    return hashlib.sha256(_canon(proof or {})).hexdigest()


def _sign(payload: dict) -> dict | None:
    key = settings.NODE_SIGNING_KEY
    if not key:
        return None
    sk = SigningKey(_unb64(key))
    return {"node_id": settings.NODE_ID, "public_key": _b64(bytes(sk.verify_key)),
            "payload": payload, "value": _b64(sk.sign(_canon(payload)).signature)}


def match_attestation(query_id: str, commitment: str) -> dict | None:
    """Signed by the node that holds the match, and by nobody else."""
    return _sign({"kind": "match", "query_id": query_id, "commitment": commitment,
                  "node_id": settings.NODE_ID})


def wrap_hop(proof: dict | None, *, query_id: str, commitment: str, from_node: str) -> dict | None:
    """Add this node's link to a proof it is passing on."""
    inner = proof or {}
    hop = _sign({"kind": "hop", "query_id": query_id, "commitment": commitment,
                 "node_id": settings.NODE_ID, "from_node": from_node,
                 "inner_hash": proof_hash(inner)})
    if hop is None:
        return None
    return {"match": inner.get("match"), "hops": list(inner.get("hops") or []) + [hop],
            "inner_hash": hop["payload"]["inner_hash"]}


def new_proof(match: dict | None) -> dict | None:
    return {"match": match, "hops": []} if match else None


def _verify_signature(att: dict) -> bool:
    try:
        VerifyKey(_unb64(att["public_key"])).verify(_canon(att["payload"]), _unb64(att["value"]))
        return True
    except (BadSignatureError, KeyError, ValueError, TypeError):
        return False


def verify_proof(proof: dict | None, *, query_id: str, commitment: str, path: list[str],
                 anchor_node: str | None, anchor_public_key: str | None) -> dict:
    """Check that a result's proof supports what it claims.

    `anchor_node` is the peer this answer arrived from, and `anchor_public_key` the key on
    file for it. That is the one identity the verifier knows first-hand; the rest of the
    chain is checked against itself.
    """
    problems: list[str] = []
    if not proof:
        return {"proven": False, "problems": ["no proof: the answering node does not sign"], "degree": None}

    match = proof.get("match")
    hops = proof.get("hops") or []

    if not match or not _verify_signature(match):
        problems.append("the match is not signed by the node that claims to hold it")
    else:
        p = match["payload"]
        if p.get("query_id") != query_id or p.get("commitment") != commitment:
            problems.append("the match attestation answers a different question")
        if p.get("node_id") != match.get("node_id"):
            problems.append("the match attestation names a different node than it is signed by")
        if path and p.get("node_id") != path[-1]:
            problems.append(f"the match is attested by {p.get('node_id')!r} but the path ends at {path[-1]!r}")

    # Walk the chain from the match outwards: each hop commits to the hash of what it received.
    inner: dict = {"match": match, "hops": []}
    for hop in hops:
        if not _verify_signature(hop):
            problems.append(f"a hop attestation from {hop.get('node_id')!r} does not verify")
            break
        p = hop["payload"]
        if p.get("query_id") != query_id or p.get("commitment") != commitment:
            problems.append("a hop attestation answers a different question")
            break
        if p.get("inner_hash") != proof_hash(inner):
            problems.append(f"the chain is broken at {p.get('node_id')!r}: a link is missing or was replaced")
            break
        if p.get("node_id") != hop.get("node_id"):
            problems.append("a hop attestation names a different node than it is signed by")
            break
        inner = {"match": match, "hops": inner["hops"] + [hop]}

    # The answer must have come from the peer we think it did, with the key we hold for it.
    # Either that peer relayed it (its hop is outermost) or it holds the match itself.
    if anchor_node:
        outer = hops[-1] if hops else match
        if not outer:
            problems.append(f"{anchor_node!r} passed on an answer without signing anything")
        elif outer.get("node_id") != anchor_node:
            problems.append(f"the outermost signature is {outer.get('node_id')!r}, not the peer it came from")
        elif anchor_public_key and outer.get("public_key") != anchor_public_key:
            problems.append(f"{anchor_node!r} signed with a key this node does not hold for it")

    # One signature per node beyond the origin: the far end signs the match, every node in
    # between signs a hop. Claiming fewer hops than the chain shows is how a degree is shortened.
    if path:
        expected_hops = max(len(path) - 2, 0)
        if len(hops) != expected_hops:
            problems.append(f"the path claims {len(path) - 1} hop(s), which needs {expected_hops} "
                            f"relay signature(s); the chain carries {len(hops)}")

    return {"proven": not problems, "problems": problems,
            "degree": len(hops) + 1 if match else (len(path) - 1 if path else None)}
