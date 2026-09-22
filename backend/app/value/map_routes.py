"""The value map: needs and capacities, shareable slices, and commitment discovery (WP-012)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agents.auth import ROLE_AGENT
from app.core.auth import ROLE_ADMIN, ROLE_AUDITOR, ROLE_USER, get_current_user, require_any_role
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db
from app.value.forwarding import (
    check_peer_rate,
    commitment_fingerprint,
    search,
    seal_confidences,
    verify_request,
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


class FederatedQueryIn(QueryIn):
    max_degree: int | None = Field(default=None, ge=0, le=6)
    min_confidence: float = Field(0.0, ge=0, le=1)


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
    result = seal_confidences(search(db, commitment=target, ttl=ttl, path=[], asked_by=principal["sub"],
                                     direction="local"))
    results = [r for r in result["results"] if (r.get("confidence") or 0) >= payload.min_confidence]
    return {
        "commitment": target,
        "epoch": current_epoch(),
        "asked": {"max_degree": ttl, "min_confidence": payload.min_confidence},
        "found": len(results),
        "results": results,
        "note": "Each result is a path and its confidence. To go further, ask the nodes on the path "
                "for an introduction; every hop, and the holder, may refuse.",
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
                                   direction="inbound", peer_node_id=peer.node_id))


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
