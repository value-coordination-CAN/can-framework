"""The value map: needs and capacities, shareable slices, and commitment discovery (WP-012)."""
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.auth import ROLE_AGENT
from app.core.auth import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_USER,
    get_current_principal,
    get_current_user,
    has_any_role,
    require_any_role,
)
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.bridge.models import Project
from app.value.agreements import (
    AGREEMENT_PROFILE,
    AgreementRecord,
    build_agreement_document,
    link_locally,
)
from app.value.documents import trusted_nodes, verify_document
from app.value.forwarding import (
    check_peer_rate,
    check_proofs,
    commitment_fingerprint,
    search,
    seal_confidences,
    verify_request,
)
from app.value.introductions import (
    Introduction,
    commit_offer,
    decide,
    receive,
    receive_commit,
    receive_reply,
    start,
)
from app.value.peer_models import Peer, QueryLog
from app.value.access import visible_assets
from app.value.commitments import (
    ATTRIBUTES,
    answer_query,
    check_rate,
    commitment,
    commitment_for,
    current_epoch,
    discovery_rules,
    epoch_salt,
    matching_items,
    period_of,
)
from app.value.documents import build_map_slice
from app.value.map_models import ITEM_TYPES, MapItem
from app.value.models import Asset

router = APIRouter()


class MapItemIn(BaseModel):
    item_type: str = Field(..., pattern="^(capacity|need)$")
    item_class: str = Field(..., min_length=1, max_length=100, description="e.g. covered_workshop, cold_storage")
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=50)
    region: str = Field(..., min_length=2, max_length=50, description="Coarse: e.g. GCC-E, UK-NW")
    available_from: date | None = None
    available_until: date | None = None
    asset_id: str | None = None
    attributes: dict | None = None
    discoverable: bool = Field(default=False, description="Opt in to being findable by other nodes")


class MapItemUpdate(BaseModel):
    discoverable: bool | None = None
    status: str | None = Field(default=None, pattern="^(open|matched|closed)$")
    quantity: float | None = Field(default=None, ge=0)
    available_until: date | None = None


class MapItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: object
    holder_user_id: str
    item_type: str
    item_class: str
    title: str
    description: str | None
    quantity: float | None
    unit: str | None
    region: str
    available_from: date | None
    available_until: date | None
    asset_id: str | None
    attributes: dict | None
    discoverable: bool
    status: str


class SliceIn(BaseModel):
    item_ids: list[str] | None = Field(default=None, description="Defaults to all your open items")
    asset_ids: list[str] | None = None
    include: list[str] | None = Field(default=None, description="Disclose only these: capacity, need, asset")
    purpose: str | None = Field(default=None, max_length=300, description="Why it is being shared")


class QueryIn(BaseModel):
    commitment: str | None = Field(default=None, min_length=64, max_length=64)
    item_type: str | None = Field(default=None, pattern="^(capacity|need)$")
    item_class: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=50)
    period: str | None = Field(default=None, max_length=10, description="e.g. 2027-Q1")


@router.get("/discovery")
def discovery_terms():
    """How to form a commitment for this node's network, and the limits on asking.
    Public: a searcher needs this before it can ask anything."""
    return {
        "epoch": current_epoch(),
        "epoch_salt": epoch_salt(),
        "attributes": list(ATTRIBUTES),
        "rules": discovery_rules(),
        "note": "Form a commitment over the coarse attributes, then ask. A node answers match or "
                "no match, never a listing, and only where at least k items share the commitment.",
    }


@router.post("/items", response_model=MapItemOut, status_code=201)
def create_item(payload: MapItemIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Record what you have spare, or what you need. Discoverability is opt-in."""
    if payload.asset_id and db.get(Asset, payload.asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    item = MapItem(holder_user_id=me.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/items", response_model=list[MapItemOut])
def list_items(item_type: str | None = Query(None, pattern="^(capacity|need)$"),
               db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    q = db.query(MapItem).filter(MapItem.holder_user_id == me.id)
    if item_type:
        q = q.filter(MapItem.item_type == item_type)
    return q.order_by(MapItem.created_at).all()


@router.patch("/items/{item_id}", response_model=MapItemOut)
def update_item(item_id: str, payload: MapItemUpdate, db: Session = Depends(get_db),
                me: User = Depends(get_current_user)):
    item = db.get(MapItem, item_id)
    if not item or item.holder_user_id != me.id:
        raise HTTPException(status_code=404, detail="item not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}")
def delete_item(item_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    item = db.get(MapItem, item_id)
    if not item or item.holder_user_id != me.id:
        raise HTTPException(status_code=404, detail="item not found")
    db.delete(item)
    db.commit()
    return {"deleted": item_id}


@router.get("/items/{item_id}/commitment")
def item_commitment(item_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """What this item looks like to a searcher: the coarse attributes, and nothing finer."""
    item = db.get(MapItem, item_id)
    if not item or item.holder_user_id != me.id:
        raise HTTPException(status_code=404, detail="item not found")
    return {
        "item_id": item.id,
        "discoverable": item.discoverable,
        "epoch": current_epoch(),
        "coarse_attributes": {"item_type": item.item_type, "item_class": item.item_class,
                              "region": item.region, "period": period_of(item)},
        "commitment": commitment_for(item),
        "note": "This is all a searcher can match on. Everything finer comes after an introduction.",
    }


@router.post("/query")
def query(payload: QueryIn, db: Session = Depends(get_db),
          principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    """Ask whether anything matching exists here. The answer is match or no match."""
    target = payload.commitment
    if not target:
        if not (payload.item_type and payload.item_class and payload.region and payload.period):
            raise HTTPException(status_code=422,
                                detail="give a commitment, or all of item_type, item_class, region and period")
        target = commitment(payload.item_type, payload.item_class, payload.region, payload.period)
    try:
        check_rate(principal["sub"])
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": "3600"})
    return answer_query(db, target)


@router.post("/slice")
def export_slice(payload: SliceIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Share a slice of your map: chosen needs, capacities and assets, as a document that
    can be verified elsewhere and redacted without breaking verification."""
    items = db.query(MapItem).filter(MapItem.holder_user_id == me.id)
    items = items.filter(MapItem.id.in_(payload.item_ids)).all() if payload.item_ids \
        else items.filter(MapItem.status == "open").all()
    assets = []
    if payload.asset_ids:
        mine = {a.id for a in db.query(Asset.id).filter(Asset.holder_user_id == me.id)}
        missing = set(payload.asset_ids) - mine
        if missing:
            raise HTTPException(status_code=403, detail=f"not yours to share: {sorted(missing)}")
        assets = db.query(Asset).filter(Asset.id.in_(payload.asset_ids)).all()
    include = set(payload.include) if payload.include else None
    if include and not include <= set(ITEM_TYPES) | {"asset"}:
        raise HTTPException(status_code=422, detail=f"include must be from {sorted(set(ITEM_TYPES) | {'asset'})}")
    return build_map_slice(db, me.id, items, assets, include=include, purpose=payload.purpose)


# --- peering and forwarding (WP-012 §5) ------------------------------------------------

class PeerIn(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=100)
    public_key: str = Field(..., min_length=20, max_length=100, description="base64url Ed25519")
    base_url: str | None = Field(default=None, max_length=300, description="Omit for inbound-only peers")
    trust_weight: float = Field(0.5, ge=0, le=1, description="How much this hop is worth")
    max_queries_per_hour: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = Field(default=None, max_length=2000)


class PeerUpdate(BaseModel):
    trust_weight: float | None = Field(default=None, ge=0, le=1)
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    base_url: str | None = Field(default=None, max_length=300)
    max_queries_per_hour: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = Field(default=None, max_length=2000)


class PeerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    base_url: str | None
    public_key: str
    trust_weight: float
    status: str
    max_queries_per_hour: int | None
    note: str | None
    last_seen_at: object | None
    # Connection value: carrying builds weight; not carrying is only a chance not taken.
    carried_count: int
    connections_count: int
    missed_count: int


class FederatedQueryIn(QueryIn):
    max_degree: int | None = Field(default=None, ge=0, le=6)
    min_confidence: float = Field(0.0, ge=0, le=1)
    proven_only: bool = Field(default=False, description="Drop results whose path proof does not verify")


@router.post("/peers", response_model=PeerOut, status_code=201)
def add_peer(payload: PeerIn, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_ADMIN))):
    """Peering is deliberate: the node operator adds each peer, with its own weight and limit."""
    if payload.node_id == settings.NODE_ID:
        raise HTTPException(status_code=422, detail="a node cannot peer with itself")
    if db.query(Peer).filter(Peer.node_id == payload.node_id).first():
        raise HTTPException(status_code=409, detail="already a peer")
    peer = Peer(added_by=principal["sub"], **payload.model_dump())
    db.add(peer)
    db.commit()
    db.refresh(peer)
    return peer


@router.get("/peers", response_model=list[PeerOut])
def list_peers(db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_ADMIN, ROLE_AUDITOR))):
    return db.query(Peer).order_by(Peer.created_at).all()


@router.patch("/peers/{peer_id}", response_model=PeerOut)
def update_peer(peer_id: str, payload: PeerUpdate, db: Session = Depends(get_db),
                principal=Depends(require_any_role(ROLE_ADMIN))):
    peer = db.get(Peer, peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="peer not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(peer, field, value)
    db.commit()
    db.refresh(peer)
    return peer


@router.delete("/peers/{peer_id}")
def remove_peer(peer_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_ADMIN))):
    peer = db.get(Peer, peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="peer not found")
    db.delete(peer)
    db.commit()
    return {"removed": peer_id}


@router.post("/query/federated")
def federated_query(payload: FederatedQueryIn, db: Session = Depends(get_db),
                    principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    """Ask this node and, through it, its peers: how far away is a match, and how much
    confidence does the chain of trust weights support? Paths come back, never contents."""
    rules = discovery_rules()
    target = payload.commitment
    if not target:
        if not (payload.item_type and payload.item_class and payload.region and payload.period):
            raise HTTPException(status_code=422,
                                detail="give a commitment, or all of item_type, item_class, region and period")
        target = commitment(payload.item_type, payload.item_class, payload.region, payload.period)
    try:
        check_rate(principal["sub"])
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e), headers={"Retry-After": "3600"})

    ttl = payload.max_degree if payload.max_degree is not None else int(rules.get("max_degree_default", 3))
    query_id = secrets.token_hex(16)  # binds every proof to this question, so none can be replayed
    result = seal_confidences(search(db, commitment=target, ttl=ttl, path=[], asked_by=principal["sub"],
                                     direction="local", query_id=query_id))
    result = check_proofs(db, result, query_id=query_id, commitment=target)
    results = [r for r in result["results"] if (r.get("confidence") or 0) >= payload.min_confidence]
    if payload.proven_only:
        results = [r for r in results if r.get("proven")]
    return {
        "commitment": target,
        "query_id": query_id,
        "epoch": current_epoch(),
        "asked": {"max_degree": ttl, "min_confidence": payload.min_confidence,
                  "proven_only": payload.proven_only},
        "found": len(results),
        "results": results,
        "note": "Each result is a path, its confidence and a proof. A proven result carries a signature "
                "from the node that holds the match and one from every hop it came through, so a degree "
                "cannot be shortened and a match cannot be claimed on someone else's behalf.",
    }


@router.post("/peer/query")
def peer_query(envelope: dict, db: Session = Depends(get_db)):
    """Peer-to-peer: a signed query from another node. No user account is involved."""
    try:
        peer = verify_request(db, envelope)
        check_peer_rate(peer)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    body = envelope.get("body") or {}
    target, ttl, path = body.get("commitment"), int(body.get("ttl", 0)), list(body.get("path") or [])
    if not target or len(target) != 64:
        raise HTTPException(status_code=422, detail="a commitment is required")
    if settings.NODE_ID in path:
        return {"node_id": settings.NODE_ID, "results": [], "note": "already visited: not answering twice"}
    return seal_confidences(search(db, commitment=target, ttl=ttl, path=path, asked_by=None,
                                   direction="inbound", peer_node_id=peer.node_id,
                                   query_id=str(body.get("query_id") or "")))


# --- introductions (WP-012 §5) ---------------------------------------------------------

class IntroductionIn(BaseModel):
    paths: list[list[str]] = Field(..., min_length=1,
                                   description="One or more routes, each starting with this node")
    commitment: str | None = Field(default=None, min_length=64, max_length=64)
    item_type: str | None = Field(default=None, pattern="^(capacity|need)$")
    item_class: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=50)
    period: str | None = Field(default=None, max_length=10)
    message: str = Field(..., min_length=1, max_length=500, description="Why you are asking")
    offer: str = Field(..., min_length=1, max_length=500,
                       description="What you undertake if they say yes. An introduction is an offer, not a ping.")


class CommitIn(BaseModel):
    contact: str = Field(..., min_length=3, max_length=300, description="How they reach you")
    note: str | None = Field(default=None, max_length=2000)


class IntroductionDecisionIn(BaseModel):
    accept: bool
    note: str | None = Field(default=None, max_length=2000)
    reply_contact: str | None = Field(default=None, max_length=300,
                                      description="How to reach you: only sent if you accept")
    share_items: list[str] | None = Field(default=None, description="Items to share as a slice, if you wish")


def _intro_out(intro: Introduction, *, mine: bool) -> dict:
    out = {
        "id": intro.id, "correlation_id": intro.correlation_id, "role": intro.role,
        "path": intro.path, "hop_index": intro.hop_index, "status": intro.status,
        "message": intro.message, "offer": intro.offer, "commit_status": intro.commit_status,
        "created_at": intro.created_at, "expires_at": intro.expires_at,
        "decision_note": intro.decision_note, "from_node": intro.from_node,
        "blocked_by": intro.blocked_by,
    }
    if intro.routes:
        out["routes"] = intro.routes
    if mine:  # contact and slice travel only to the person who asked
        out |= {"reply_contact": intro.reply_contact, "reply_slice": intro.reply_slice}
    if intro.role == "destination" and intro.commit_status == "committed":
        out["requester_contact"] = intro.requester_contact  # they committed: now they are reachable
    if intro.role == "destination":
        out["candidate_items"] = intro.candidate_items
    return out


@router.post("/introductions", status_code=201)
def request_introduction(payload: IntroductionIn, db: Session = Depends(get_db),
                         principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT))):
    """Ask to be introduced along a path a query returned. Every hop, and the far end, may refuse."""
    target = payload.commitment
    if not target:
        if not (payload.item_type and payload.item_class and payload.region and payload.period):
            raise HTTPException(status_code=422,
                                detail="give a commitment, or all of item_type, item_class, region and period")
        target = commitment(payload.item_type, payload.item_class, payload.region, payload.period)
    try:
        intro = start(db, paths=payload.paths, commitment=target, message=payload.message,
                      offer=payload.offer, requested_by=principal["sub"])
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _intro_out(intro, mine=True)


@router.get("/introductions")
def list_introductions(db: Session = Depends(get_db), me: User = Depends(get_current_user),
                       principal=Depends(get_current_principal)):
    """Yours to answer: ones you asked for, ones waiting on your items, and — for the node
    operator — ones waiting on this node to pass along."""
    rows = db.query(Introduction).order_by(Introduction.created_at.desc()).limit(200).all()
    my_items = {i.id for i in db.query(MapItem.id).filter(MapItem.holder_user_id == me.id)}
    is_operator = has_any_role(principal, ROLE_ADMIN, ROLE_AUDITOR)
    out = []
    for r in rows:
        mine = r.requested_by == principal["sub"]
        concerns_me = bool(set(r.candidate_items or []) & my_items)
        if mine or concerns_me or is_operator:
            out.append(_intro_out(r, mine=mine) | {"awaiting_you": (concerns_me or is_operator) and r.status == "pending"})
    return out


@router.post("/introductions/{intro_id}/decision")
def decide_introduction(intro_id: str, payload: IntroductionDecisionIn, db: Session = Depends(get_db),
                        me: User = Depends(get_current_user), principal=Depends(get_current_principal)):
    """Pass it on, or refuse. At the far end, accepting means choosing how to be reached,
    and optionally sharing a slice."""
    intro = db.get(Introduction, intro_id)
    if not intro:
        raise HTTPException(status_code=404, detail="introduction not found")
    my_items = {i.id for i in db.query(MapItem.id).filter(MapItem.holder_user_id == me.id)}
    is_holder = bool(set(intro.candidate_items or []) & my_items)
    if intro.role == "relay" and not has_any_role(principal, ROLE_ADMIN):
        raise HTTPException(status_code=403, detail="only the node operator decides whether to pass a request on")
    if intro.role == "destination" and not (is_holder or has_any_role(principal, ROLE_ADMIN)):
        raise HTTPException(status_code=403, detail="only a holder of the matching items can answer this")
    if intro.role == "origin":
        raise HTTPException(status_code=422, detail="this is your own request; nothing to decide")

    reply_slice = None
    if payload.accept and payload.share_items:
        items = db.query(MapItem).filter(MapItem.id.in_(payload.share_items),
                                         MapItem.holder_user_id == me.id).all()
        if len(items) != len(payload.share_items):
            raise HTTPException(status_code=403, detail="you can only share your own items")
        reply_slice = build_map_slice(db, me.id, items, [], purpose="introduction")

    try:
        intro = decide(db, intro, accept=payload.accept, note=payload.note, decided_by=principal["sub"],
                       reply_contact=payload.reply_contact, reply_slice=reply_slice)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _intro_out(intro, mine=False)


@router.post("/introductions/{intro_id}/commit")
def commit_introduction(intro_id: str, payload: CommitIn, db: Session = Depends(get_db),
                        principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT))):
    """The far end said yes; now you stand behind your offer. Your contact travels to them
    along the route that got through, and not before."""
    intro = db.get(Introduction, intro_id)
    if not intro or intro.requested_by != principal["sub"]:
        raise HTTPException(status_code=404, detail="introduction not found")
    try:
        intro = commit_offer(db, intro, contact=payload.contact, note=payload.note,
                             by_subject=principal["sub"])
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _intro_out(intro, mine=True)


class AgreementIn(BaseModel):
    kind: str = Field(..., pattern="^(contribution|supply|access)$")
    terms: str = Field(..., min_length=1, max_length=5000, description="What was agreed, in words")
    value: float | None = Field(default=None, ge=0, description="What it is worth, if you have valued it")
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    # Both parties on this node? Then it can become a stake straight away.
    project_id: str | None = None
    counterpart_user_id: str | None = None
    source_type: str | None = Field(default=None, description="For a contribution: overrides the default")
    cash_share: float = Field(1.0, ge=0, le=1, description="For a supply agreement")


class AgreementLinkIn(BaseModel):
    project_id: str
    counterpart_user_id: str
    source_type: str | None = None
    cash_share: float = Field(1.0, ge=0, le=1)


def _agreement_out(rec: AgreementRecord) -> dict:
    return {
        "id": rec.id, "created_at": rec.created_at, "correlation_id": rec.correlation_id,
        "introduction_id": rec.introduction_id, "kind": rec.kind, "terms": rec.terms,
        "offer": rec.offer, "value": rec.value, "currency": rec.currency,
        "counterpart_node": rec.counterpart_node, "counterpart_contact": rec.counterpart_contact,
        "status": rec.status, "linked_type": rec.linked_type, "linked_id": rec.linked_id,
        "project_id": rec.project_id, "document": rec.document,
    }


@router.post("/introductions/{intro_id}/agreement", status_code=201)
def record_agreement(intro_id: str, payload: AgreementIn, db: Session = Depends(get_db),
                     me: User = Depends(get_current_user), principal=Depends(get_current_principal)):
    """Turn a committed introduction into a record — and, where both parties are here, into
    a WP-010 contribution or supplier agreement, so the work earns a stake rather than goodwill."""
    intro = db.get(Introduction, intro_id)
    if not intro:
        raise HTTPException(status_code=404, detail="introduction not found")
    my_items = {i.id for i in db.query(MapItem.id).filter(MapItem.holder_user_id == me.id)}
    is_party = intro.requested_by == principal["sub"] or bool(set(intro.candidate_items or []) & my_items)
    if not (is_party or has_any_role(principal, ROLE_ADMIN)):
        raise HTTPException(status_code=403, detail="only a party to the introduction can record what was agreed")
    if intro.status != "accepted" or intro.commit_status != "committed":
        raise HTTPException(status_code=409,
                            detail="record an agreement once the far end has accepted and the near side has committed")

    far_end = intro.path[-1] if intro.role == "origin" else intro.path[0]
    rec = AgreementRecord(
        correlation_id=intro.correlation_id, introduction_id=intro.id, kind=payload.kind,
        terms=payload.terms, offer=intro.offer, value=payload.value, currency=payload.currency,
        recorded_by=principal["sub"],
        counterpart_node=None if far_end == settings.NODE_ID else far_end,
        counterpart_contact=intro.reply_contact if intro.role == "origin" else intro.requester_contact,
    )
    db.add(rec)
    db.flush()
    rec.document = build_agreement_document(rec, parties={
        "recorded_by_node": settings.NODE_ID, "counterpart_node": rec.counterpart_node,
        "introduction": intro.correlation_id,
    })
    db.commit()
    db.refresh(rec)

    created = None
    if payload.project_id and payload.counterpart_user_id:
        project = db.get(Project, payload.project_id)
        counterpart = db.get(User, payload.counterpart_user_id)
        if not project or not counterpart:
            raise HTTPException(status_code=404, detail="project or counterpart not found here")
        try:
            created = link_locally(db, rec, project=project, counterpart=counterpart, caller=me,
                                   source_type=payload.source_type, cash_share=payload.cash_share)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    return {
        "agreement": _agreement_out(rec),
        "created": created,
        "note": ("Recorded as a stake on this node." if created else
                 "Recorded. Send the document to the other node; a stake is created there by a local party, "
                 "deliberately, because a contributor needs an identity someone has vouched for."),
    }


@router.get("/agreements")
def list_agreements(db: Session = Depends(get_db), me: User = Depends(get_current_user),
                    principal=Depends(get_current_principal)):
    q = db.query(AgreementRecord)
    if not has_any_role(principal, ROLE_ADMIN, ROLE_AUDITOR):
        q = q.filter(AgreementRecord.recorded_by == principal["sub"])
    return [_agreement_out(r) for r in q.order_by(AgreementRecord.created_at.desc()).limit(200)]


@router.post("/agreements/{agreement_id}/link")
def link_agreement(agreement_id: str, payload: AgreementLinkIn, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)):
    """Attach an agreement recorded earlier, or received from another node, to a project here."""
    rec = db.get(AgreementRecord, agreement_id)
    if not rec:
        raise HTTPException(status_code=404, detail="agreement not found")
    project = db.get(Project, payload.project_id)
    counterpart = db.get(User, payload.counterpart_user_id)
    if not project or not counterpart:
        raise HTTPException(status_code=404, detail="project or counterpart not found here")
    try:
        created = link_locally(db, rec, project=project, counterpart=counterpart, caller=me,
                               source_type=payload.source_type, cash_share=payload.cash_share)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"agreement": _agreement_out(rec), "created": created}


@router.post("/agreements/import", status_code=201)
def import_agreement(document: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Take the other side's record of what was agreed. It is stored and verifiable; it does
    not become a stake here until a local party attaches it to a project."""
    report = verify_document(document, trusted_nodes())
    if not report["valid"]:
        raise HTTPException(status_code=422, detail={"message": "document does not verify", "report": report})
    if document.get("header", {}).get("profile") != AGREEMENT_PROFILE:
        raise HTTPException(status_code=422, detail="that is not an agreement document")
    body = document.get("agreement") or {}
    header = document["header"]
    rec = AgreementRecord(
        correlation_id=header.get("subject", {}).get("correlation_id", ""), kind=body.get("kind", "contribution"),
        terms=body.get("terms", ""), offer=body.get("offer"), value=body.get("value"),
        currency=body.get("currency"), recorded_by=me.subject or me.id,
        counterpart_node=header.get("node_id"), document=document,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"agreement": _agreement_out(rec), "verification": report}


@router.post("/peer/introduction/commit")
def peer_introduction_commit(envelope: dict, db: Session = Depends(get_db)):
    """A commitment travelling up the path to the far end."""
    try:
        peer = verify_request(db, envelope)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        intro = receive_commit(db, body=envelope.get("body") or {}, from_node=peer.node_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if intro is None:
        raise HTTPException(status_code=404, detail="no such introduction here")
    return {"correlation_id": intro.correlation_id, "commit_status": intro.commit_status}


@router.post("/peer/introduction")
def peer_introduction(envelope: dict, db: Session = Depends(get_db)):
    """A signed introduction request handed over by the previous node on the path."""
    try:
        peer = verify_request(db, envelope)
        check_peer_rate(peer)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        intro = receive(db, body=envelope.get("body") or {}, from_node=peer.node_id)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"correlation_id": intro.correlation_id, "status": intro.status, "role": intro.role,
            "note": "Held for a decision here. Nobody is contactable merely for being on a graph."}


@router.post("/peer/introduction/reply")
def peer_introduction_reply(envelope: dict, db: Session = Depends(get_db)):
    """An answer travelling back down the path."""
    try:
        peer = verify_request(db, envelope)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    try:
        intro = receive_reply(db, body=envelope.get("body") or {}, from_node=peer.node_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if intro is None:
        raise HTTPException(status_code=404, detail="no such introduction here")
    return {"correlation_id": intro.correlation_id, "status": intro.status}


@router.get("/queries")
def query_log(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
              principal=Depends(require_any_role(ROLE_ADMIN, ROLE_AUDITOR))):
    """Who has been asking this node what. Commitments only: the log does not reveal
    what was being looked for either."""
    rows = db.query(QueryLog).order_by(QueryLog.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "created_at": r.created_at, "direction": r.direction, "peer_node_id": r.peer_node_id,
             "asked_by": r.asked_by, "commitment": commitment_fingerprint(r.commitment), "ttl": r.ttl,
             "path": r.path, "matched": r.matched, "results": r.results} for r in rows]


@router.get("/matches/{item_id}")
def local_matches(item_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Does anything on this node already answer this need (or use this capacity)?
    Local matching first: the nearest capacity is often on the same node."""
    item = db.get(MapItem, item_id)
    if not item or item.holder_user_id != me.id:
        raise HTTPException(status_code=404, detail="item not found")
    opposite = "need" if item.item_type == "capacity" else "capacity"
    target = commitment(opposite, item.item_class, item.region, period_of(item))
    found = [i for i in matching_items(db, target) if i.holder_user_id != me.id]
    return {
        "item_id": item.id,
        "looking_for": opposite,
        "matches_on_this_node": len(found),
        "note": "Counts only. Ask the holder for an introduction to go further; nothing is disclosed here.",
    }
