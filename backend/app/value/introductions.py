"""Introductions: how the two ends of a path actually meet (WP-012 §5).

Discovery says *a match exists, three hops away*. An introduction is the request that
travels that path so the two ends can talk — and **every hop may refuse**, including the
far end, which decides whether to answer at all and what to share if it does.

Nobody is contactable merely for being on a graph. An introduction carries a short message
and nothing else; contact details exist only in an acceptance, chosen by the person
accepting.
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.core.time import utcnow
from app.db.base import Base
from app.value.commitments import matching_items
from app.value.engine import load_value_config

STATUSES = ("pending", "forwarded", "accepted", "declined", "expired")


def _uuid() -> str:
    return str(uuid.uuid4())


def introduction_rules() -> dict:
    r = dict(load_value_config().introductions or {})
    r.setdefault("ttl_hours", 72)
    r.setdefault("max_message_chars", 500)
    r.setdefault("max_open_per_caller", 20)
    # Relays carry offers by default. An operator may set "review" to decide each one by
    # hand, at the cost of being seen to block and losing weight for it.
    r.setdefault("relay_policy", "auto")
    r.setdefault("connection_weight_gain", 0.05)
    return r


class Introduction(Base):
    """One introduction, as this node sees it. Each node on the path holds its own row,
    tied together by `correlation_id`."""
    __tablename__ = "vm_introductions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))          # origin|relay|destination
    commitment: Mapped[str] = mapped_column(String(64))
    path: Mapped[list] = mapped_column(JSON)               # node ids, origin first
    hop_index: Mapped[int] = mapped_column(Integer)        # where this node sits on the path
    message: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(400), nullable=True)   # local subject, origin only
    from_node: Mapped[str | None] = mapped_column(String(100), nullable=True)      # who handed it to us
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    decided_by: Mapped[str | None] = mapped_column(String(400), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)  # only ever set on acceptance
    reply_slice: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_items: Mapped[list | None] = mapped_column(JSON, nullable=True)      # local, destination only
    # What the asker undertakes if the far end says yes. It travels with the request:
    # an introduction is an offer, not a ping.
    offer: Mapped[str] = mapped_column(Text, default="")
    # A hop that refuses to carry an offer is named, so blocking is visible rather than silent.
    blocked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # offered -> committed (or withdrawn). The near side commits only after the far end accepts.
    commit_status: Mapped[str] = mapped_column(String(20), default="offered")
    requester_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)  # sent only on commit
    # An offer may travel several routes at once, so one hop cannot stop it. Origin only.
    routes: Mapped[list | None] = mapped_column(JSON, nullable=True)


def expiry() -> datetime:
    return utcnow() + timedelta(hours=float(introduction_rules()["ttl_hours"]))


def is_expired(intro: Introduction) -> bool:
    return intro.status in {"pending", "forwarded"} and intro.expires_at < utcnow()


def role_for(path: list[str], hop_index: int) -> str:
    if hop_index == 0:
        return "origin"
    return "destination" if hop_index == len(path) - 1 else "relay"


def candidates(db: Session, commitment: str) -> list[str]:
    """Which of this node's discoverable items the request could be about. Local only:
    it is never sent anywhere, and it is how the node knows whom to ask."""
    return [i.id for i in matching_items(db, commitment)]


def next_hop(intro: Introduction) -> str | None:
    nxt = intro.hop_index + 1
    return intro.path[nxt] if nxt < len(intro.path) else None


def previous_hop(intro: Introduction) -> str | None:
    return intro.path[intro.hop_index - 1] if intro.hop_index > 0 else None


def validate_path(path: list[str]) -> None:
    if len(path) < 2:
        raise ValueError("a path needs at least this node and one other")
    if path[0] != settings.NODE_ID:
        raise ValueError(f"a path must start at this node ({settings.NODE_ID})")
    if len(set(path)) != len(path):
        raise ValueError("a path cannot visit a node twice")


# --- the flow -------------------------------------------------------------------------

def _forward(db: Session, intro: Introduction) -> bool:
    """Hand the request to the next hop. Local import: forwarding does not know about us."""
    from app.value.forwarding import call_peer, sign_request

    nxt = next_hop(intro)
    if nxt is None:
        return False
    envelope = sign_request({
        "correlation_id": intro.correlation_id, "commitment": intro.commitment,
        "path": intro.path, "hop_index": intro.hop_index + 1, "message": intro.message,
        "offer": intro.offer,
    })
    answer = call_peer(db, nxt, envelope, "/map/peer/introduction")
    return bool(answer)


def record_missed(db: Session, node_id: str | None) -> None:
    """A route that did not carry an offer is a **missed opportunity**, not an offence.

    Nothing is deducted. The count is simply kept, and because carrying is what builds
    weight (see `credit_connection`), a node that rarely carries is gradually overtaken by
    the ones that do. Value flows where connection flows.
    """
    if not node_id:
        return
    from app.value.peer_models import Peer

    peer = db.query(Peer).filter(Peer.node_id == node_id).first()
    if peer is None:
        return
    peer.missed_count = int(peer.missed_count or 0) + 1
    db.commit()


def credit_connection(db: Session, node_id: str | None, *, carried: bool = True,
                      connected: bool = False) -> None:
    """Carrying an offer builds connection value. A hop that carries something which ends
    in an acceptance is worth more next time, because it has shown it connects people."""
    if not node_id:
        return
    from app.value.peer_models import Peer

    peer = db.query(Peer).filter(Peer.node_id == node_id).first()
    if peer is None:
        return
    if carried:
        peer.carried_count = int(peer.carried_count or 0) + 1
    if connected:
        peer.connections_count = int(peer.connections_count or 0) + 1
        gain = float(introduction_rules()["connection_weight_gain"])
        peer.trust_weight = min(1.0, round(float(peer.trust_weight or 0) + gain, 6))
    db.commit()


def _reply_back(db: Session, intro: Introduction) -> bool:
    """Send this node's answer back down the path it came from."""
    from app.value.forwarding import call_peer, sign_request

    prev = previous_hop(intro)
    if prev is None:
        return False
    envelope = sign_request({
        "correlation_id": intro.correlation_id, "status": intro.status,
        "decision_note": intro.decision_note, "reply_contact": intro.reply_contact,
        "reply_slice": intro.reply_slice, "from_hop": intro.hop_index,
        "blocked_by": intro.blocked_by,
    })
    answer = call_peer(db, prev, envelope, "/map/peer/introduction/reply")
    return bool(answer)


def _route_status(routes: list[dict]) -> str:
    """One offer, several routes: it is alive while any route is."""
    states = {r["status"] for r in routes}
    if "accepted" in states:
        return "accepted"
    if "forwarded" in states:
        return "forwarded"
    return "declined"


def start(db: Session, *, paths: list[list[str]], commitment: str, message: str, offer: str,
          requested_by: str) -> Introduction:
    for path in paths:
        validate_path(path)
    if len({tuple(p) for p in paths}) != len(paths):
        raise ValueError("the same route was given twice")
    rules = introduction_rules()
    if len(message) > int(rules["max_message_chars"]):
        raise ValueError(f"a message may be at most {rules['max_message_chars']} characters")
    open_now = db.query(Introduction).filter(
        Introduction.requested_by == requested_by,
        Introduction.status.in_(("pending", "forwarded")),
    ).count()
    if open_now >= int(rules["max_open_per_caller"]):
        raise PermissionError(f"you already have {open_now} introductions open, the limit is "
                              f"{rules['max_open_per_caller']}")

    intro = Introduction(correlation_id=uuid.uuid4().hex, role="origin", commitment=commitment,
                         path=paths[0], hop_index=0, message=message, offer=offer,
                         requested_by=requested_by, status="pending", expires_at=expiry())
    db.add(intro)
    db.commit()
    db.refresh(intro)

    routes = []
    for path in paths:
        intro.path = path  # _forward reads the route it is sending along
        if _forward(db, intro):
            routes.append({"path": path, "status": "forwarded", "blocked_by": None})
        else:
            blocker = path[1]
            record_missed(db, blocker)
            routes.append({"path": path, "status": "declined", "blocked_by": blocker,
                           "note": f"{blocker} could not be reached or is not a peer"})
    intro.path = paths[0]
    intro.routes = routes
    intro.status = _route_status(routes)
    if intro.status == "declined":
        intro.decided_at = utcnow()
        intro.blocked_by = ", ".join(r["blocked_by"] for r in routes if r["blocked_by"])
        intro.decision_note = "every route refused or was unreachable"
    db.commit()
    db.refresh(intro)
    return intro


def receive(db: Session, *, body: dict, from_node: str) -> Introduction:
    path, hop = list(body.get("path") or []), int(body.get("hop_index", 0))
    if hop >= len(path) or path[hop] != settings.NODE_ID:
        raise ValueError("this node is not at that position on the path")
    if previous_hop_of(path, hop) != from_node:
        raise ValueError("the sender is not the previous node on the path")
    existing = db.query(Introduction).filter(
        Introduction.correlation_id == body["correlation_id"]).first()
    if existing:
        # The same offer arriving by another route. One decision, not two.
        note = f"also reached here by {' → '.join(path)}"
        existing.decision_note = f"{existing.decision_note}; {note}" if existing.decision_note else note
        db.commit()
        db.refresh(existing)
        return existing

    role = role_for(path, hop)
    limit = int(introduction_rules()["max_message_chars"])
    intro = Introduction(
        correlation_id=body["correlation_id"], role=role, commitment=body["commitment"],
        path=path, hop_index=hop, message=(body.get("message") or "")[:limit],
        offer=(body.get("offer") or "")[:limit],
        from_node=from_node, status="pending", expires_at=expiry(),
        candidate_items=candidates(db, body["commitment"]) if role == "destination" else None,
    )
    db.add(intro)
    db.commit()
    db.refresh(intro)

    # An offer travels to the far end by itself. A relay carries it unless this node's
    # operator has chosen to review each one, and choosing to review means being seen to
    # hold things up.
    if role == "relay" and introduction_rules()["relay_policy"] == "auto":
        if _forward(db, intro):
            intro.status = "forwarded"
            intro.decision_note = "carried automatically: relays do not gate offers here"
        else:
            intro.status = "declined"
            intro.blocked_by = next_hop(intro)
            intro.decision_note = f"the next node ({next_hop(intro)}) could not be reached"
            record_missed(db, intro.blocked_by)
            db.commit()
            _reply_back(db, intro)
        db.commit()
        db.refresh(intro)
    return intro


def previous_hop_of(path: list[str], hop_index: int) -> str | None:
    return path[hop_index - 1] if hop_index > 0 else None


def decide(db: Session, intro: Introduction, *, accept: bool, note: str | None, decided_by: str,
           reply_contact: str | None = None, reply_slice: dict | None = None) -> Introduction:
    """A hop's answer. Relays either pass it on or refuse; the far end accepts or refuses."""
    if intro.status not in {"pending"}:
        raise ValueError(f"this introduction is already {intro.status}")
    if is_expired(intro):
        intro.status = "expired"
        db.commit()
        raise ValueError("this introduction has expired")

    intro.decided_by = decided_by
    intro.decided_at = utcnow()
    intro.decision_note = note

    if not accept:
        intro.status = "declined"
        if intro.role == "relay":
            intro.blocked_by = settings.NODE_ID  # a relay that refuses says so in its own name
        db.commit()
        _reply_back(db, intro)
        db.refresh(intro)
        return intro

    if intro.role == "relay":
        intro.status = "forwarded" if _forward(db, intro) else "declined"
        if intro.status == "declined":
            intro.decision_note = f"the next node ({next_hop(intro)}) could not be reached"
            db.commit()
            _reply_back(db, intro)
    else:  # destination
        if not reply_contact:
            raise ValueError("accepting means giving a way to be reached")
        intro.status = "accepted"
        intro.reply_contact = reply_contact
        intro.reply_slice = reply_slice
        db.commit()
        _reply_back(db, intro)
    db.commit()
    db.refresh(intro)
    return intro


def receive_reply(db: Session, *, body: dict, from_node: str) -> Introduction | None:
    intro = db.query(Introduction).filter(Introduction.correlation_id == body.get("correlation_id")).first()
    if intro is None:
        return None

    status = body.get("status", "declined")
    if intro.role == "origin" and intro.routes:
        route = next((r for r in intro.routes if len(r["path"]) > 1 and r["path"][1] == from_node), None)
        if route is None:
            raise ValueError("that reply did not come from a node this offer was sent to")
        route["status"] = status
        route["blocked_by"] = body.get("blocked_by")
        route["note"] = body.get("decision_note")
        intro.routes = list(intro.routes)  # rebind so the JSON column is written
        intro.status = _route_status(intro.routes)
        credit_connection(db, from_node, carried=True, connected=(status == "accepted"))
        if status == "accepted":
            intro.reply_contact = body.get("reply_contact")
            intro.reply_slice = body.get("reply_slice")
            intro.path = route["path"]  # the route that got through
            intro.decision_note = body.get("decision_note")
        elif intro.status == "declined":
            intro.decision_note = "every route refused"
            intro.blocked_by = ", ".join(r["blocked_by"] for r in intro.routes if r.get("blocked_by"))
        record_missed(db, body.get("blocked_by"))
        db.commit()
        db.refresh(intro)
        return intro

    if next_hop(intro) != from_node:
        raise ValueError("that reply did not come from the node it was sent to")
    credit_connection(db, from_node, carried=True, connected=(status == "accepted"))
    intro.status = status
    intro.decision_note = body.get("decision_note")
    intro.reply_contact = body.get("reply_contact")
    intro.reply_slice = body.get("reply_slice")
    intro.blocked_by = body.get("blocked_by")
    db.commit()
    _reply_back(db, intro)
    db.refresh(intro)
    return intro


def commit_offer(db: Session, intro: Introduction, *, contact: str, note: str | None,
                 by_subject: str) -> Introduction:
    """The near side commits. The far end has said yes; now the asker stands behind the
    offer and gives its own contact, which travels to the far end along the route that worked."""
    from app.value.forwarding import call_peer, sign_request

    if intro.role != "origin":
        raise ValueError("only the side that made the offer commits to it")
    if intro.status != "accepted":
        raise ValueError(f"nothing to commit to: this offer is {intro.status}")
    if intro.commit_status == "committed":
        raise ValueError("already committed")

    intro.commit_status = "committed"
    intro.requester_contact = contact
    intro.decision_note = note or intro.decision_note
    db.commit()
    envelope = sign_request({"correlation_id": intro.correlation_id, "commit_status": "committed",
                             "requester_contact": contact, "note": note, "path": intro.path})
    call_peer(db, intro.path[1], envelope, "/map/peer/introduction/commit")
    db.refresh(intro)
    return intro


def receive_commit(db: Session, *, body: dict, from_node: str) -> Introduction | None:
    """A commitment travelling up the path to the far end."""
    from app.value.forwarding import call_peer, sign_request

    intro = db.query(Introduction).filter(Introduction.correlation_id == body.get("correlation_id")).first()
    if intro is None:
        return None
    if previous_hop(intro) != from_node:
        raise ValueError("that commitment did not come from the previous node on the path")
    intro.commit_status = "committed"
    intro.requester_contact = body.get("requester_contact")
    db.commit()
    nxt = next_hop(intro)
    if nxt:
        call_peer(db, nxt, sign_request(body), "/map/peer/introduction/commit")
    db.refresh(intro)
    return intro
