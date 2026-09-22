"""WP-011 Value Assurance API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.auth import ROLE_AGENT
from app.core.auth import (
    ROLE_ADMIN,
    ROLE_ATTESTER,
    ROLE_AUDITOR,
    ROLE_REVIEWER,
    ROLE_USER,
    current_user_or_none,
    get_current_user,
    has_any_role,
    require_any_role,
)
from app.value.access import may_see_valuation, visible_assets
from app.value.documents import build_document, import_document, node_identity, trusted_nodes, verify_document
from app.value.work import ITEM_TYPES, asset_map, work_items
from app.core.time import utcnow
from app.db.models import User
from app.db.session import get_db
from app.value.agent import ACTIONS, effective_mandate, run_assurance
from app.value.engine import current_evidence, gather_inputs, load_value_config, validate_input, valuate
from app.agents.models import Agent as AgentModel
from app.value.models import Asset, AssetEvidence, AssetShare, AssuranceRun, EvidenceProposal
from app.value.schemas import (
    AssetCreate,
    AssetOut,
    EvidenceCreate,
    EvidenceOut,
    MandateIn,
    ProposalDecisionIn,
    ProposalIn,
    ProposalOut,
    RunOut,
    ShareIn,
    ShareOut,
)

router = APIRouter()

FULL = "full"


def _access(db: Session, asset: Asset, principal: dict) -> set[str] | str | None:
    """FULL for the holder and oversight roles; the shared categories for grantees; None otherwise."""
    me = current_user_or_none(principal, db)
    if me is not None and me.id == asset.holder_user_id:
        return FULL
    if has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR):
        return FULL
    if me is not None:
        share = db.query(AssetShare).filter(AssetShare.asset_id == asset.id, AssetShare.grantee_user_id == me.id).first()
        if share:
            return set(share.categories)
    return None


def _get_asset(db: Session, asset_id: str) -> Asset:
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="asset not found")
    return a


def _require_holder(asset: Asset, me: User) -> None:
    if asset.holder_user_id != me.id:
        raise HTTPException(status_code=403, detail="only the holder can do this")


@router.get("/config")
def get_config(principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER, ROLE_AUDITOR))):
    """The public model: categories, inputs, scenarios and default mandate."""
    cfg = load_value_config()
    return {
        "categories": list(cfg.categories),
        "inputs": {k: vars(v) for k, v in cfg.inputs.items()},
        "scenarios": cfg.scenarios,
        "default_mandate": cfg.default_mandate,
        "actions": sorted(ACTIONS),
    }


@router.get("/search")
def search(
    q: str | None = Query(None, max_length=200, description="Match on name, kind or description"),
    kind: str | None = Query(None, max_length=100),
    liability_only: bool = False,
    max_confidence: float | None = Query(None, ge=0, le=1, description="Only assets below this confidence"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR)),
):
    """Find assets you (or, for an agent, your steward) can see. This is how an integrating
    system discovers what there is to value, without being handed a list of everything."""
    visible = visible_assets(db, principal)
    if not visible:
        return {"count": 0, "assets": []}
    query = db.query(Asset).filter(Asset.id.in_(list(visible)))
    if q:
        like = f"%{q}%"
        query = query.filter(Asset.name.ilike(like) | Asset.kind.ilike(like) | Asset.description.ilike(like))
    if kind:
        query = query.filter(Asset.kind == kind)

    out = []
    for a in query.order_by(Asset.created_at.desc()).limit(limit * 2):
        access = visible[a.id]
        row = {"id": a.id, "name": a.name, "kind": a.kind, "currency": a.currency,
               "access": "full" if access == FULL else sorted(access)}
        if may_see_valuation(access):
            v = valuate(gather_inputs(current_evidence(db, a.id)))
            row |= {"complete": v["complete"], "confidence": v["confidence"],
                    "value": v["base"]["value"] if v["complete"] else None,
                    "is_liability": v["base"]["is_liability"] if v["complete"] else None,
                    "missing_inputs": v["missing_inputs"]}
            if liability_only and not (v["complete"] and (v["base"]["is_liability"] or
                                                          any(s["is_liability"] for s in v["scenarios"].values()))):
                continue
            if max_confidence is not None and v["confidence"] > max_confidence:
                continue
        elif liability_only or max_confidence is not None:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return {"count": len(out), "assets": out}


@router.get("/node")
def node():
    """This node's identity for document exchange: who it is, and whether it signs."""
    return {**node_identity(), "trusted_nodes": sorted(trusted_nodes())}


@router.get("/assets/{asset_id}/document")
def export_document(
    asset_id: str,
    disclose: str | None = Query(None, description="Comma-separated categories to reveal; the rest are withheld"),
    include_valuation: bool = True,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR)),
):
    """Export the asset as a portable document: self-describing, hashed item by item,
    redactable without breaking verification, and signed if this node has a key."""
    a = _get_asset(db, asset_id)
    access = visible_assets(db, principal).get(a.id)
    if access is None:
        raise HTTPException(status_code=403, detail="not allowed to view this asset")
    categories = {c.strip() for c in disclose.split(",")} if disclose else None
    if categories:
        unknown = categories - set(load_value_config().categories)
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown categories {sorted(unknown)}")
    return build_document(db, a, access, disclose=categories, include_valuation=include_valuation)


@router.post("/documents/verify")
def verify_doc(document: dict, principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    """Check a document from anywhere: hashes, root and signature. No trust required."""
    return verify_document(document, trusted_nodes())


@router.post("/documents/import")
def import_doc(document: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Take a document from another node into this one. Evidence from an untrusted node is
    held as unverified: another node's word is not this node's evidence."""
    report = verify_document(document, trusted_nodes())
    if not report["valid"]:
        raise HTTPException(status_code=422, detail={"message": "document does not verify", "report": report})
    result = import_document(db, document, me.id, report)
    return {"verification": report, **result}


@router.get("/work")
def work(limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db),
         principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    """What needs looking at: missing or stale evidence, low confidence, liability risk,
    assessments due, and proposals waiting. The queue an integrating system works from."""
    items = work_items(db, visible_assets(db, principal), limit=limit)
    return {"count": len(items), "item_types": ITEM_TYPES, "items": items}


@router.post("/assets", response_model=AssetOut)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    a = Asset(holder_user_id=me.id, **payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.get("/assets")
def list_assets(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    own = db.query(Asset).filter(Asset.holder_user_id == me.id).order_by(Asset.created_at).all()
    shares = db.query(AssetShare).filter(AssetShare.grantee_user_id == me.id).all()
    shared = []
    for s in shares:
        a = db.get(Asset, s.asset_id)
        if a:
            shared.append({**AssetOut.model_validate(a).model_dump(mode="json"), "shared_categories": s.categories})
    return {"held": [AssetOut.model_validate(a).model_dump(mode="json") for a in own], "shared_with_me": shared}


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER, ROLE_AUDITOR))):
    a = _get_asset(db, asset_id)
    access = _access(db, a, principal)
    if access is None and not has_any_role(principal, ROLE_ATTESTER):
        raise HTTPException(status_code=403, detail="not allowed to view this asset")
    evidence = current_evidence(db, a.id)
    if access != FULL:
        allowed = access or set()
        evidence = [e for e in evidence if e.category in allowed]
    return {
        "asset": AssetOut.model_validate(a).model_dump(mode="json"),
        "access": "full" if access == FULL else sorted(access or []),
        "evidence": [EvidenceOut.model_validate(e).model_dump(mode="json") for e in evidence],
        "mandate": effective_mandate(a, load_value_config().default_mandate) if access == FULL else None,
    }


@router.get("/assets/{asset_id}/evidence/history", response_model=list[EvidenceOut])
def evidence_history(asset_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_AUDITOR))):
    a = _get_asset(db, asset_id)
    if _access(db, a, principal) != FULL:
        raise HTTPException(status_code=403, detail="only the holder and oversight roles see full history")
    return db.query(AssetEvidence).filter(AssetEvidence.asset_id == a.id).order_by(AssetEvidence.recorded_at).all()


@router.post("/assets/{asset_id}/evidence", response_model=EvidenceOut)
def add_evidence(
    asset_id: str,
    payload: EvidenceCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER)),
):
    """Holders record evidence about their own assets (self-reported). Attesters record
    attested evidence with a reference. Newer evidence for the same key supersedes older."""
    a = _get_asset(db, asset_id)
    cfg = load_value_config()
    me = current_user_or_none(principal, db)
    is_holder = me is not None and me.id == a.holder_user_id
    if not is_holder and not has_any_role(principal, ROLE_ATTESTER):
        raise HTTPException(status_code=403, detail="only the holder or an attester can add evidence")
    if not is_holder and not payload.evidence_ref:
        raise HTTPException(status_code=422, detail="evidence_ref is required for attested evidence")
    if payload.category not in cfg.categories:
        raise HTTPException(status_code=422, detail=f"category must be one of {list(cfg.categories)}")
    d = cfg.inputs.get(payload.key)
    if d is not None:
        if payload.category != d.category:
            raise HTTPException(status_code=422, detail=f"{payload.key} belongs to category '{d.category}'")
        if payload.value is None:
            raise HTTPException(status_code=422, detail=f"{payload.key} needs a numeric value")
        try:
            validate_input(payload.key, payload.value)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    elif payload.value is None and not payload.text:
        raise HTTPException(status_code=422, detail="evidence needs a value or text")

    now = utcnow()
    db.query(AssetEvidence).filter(
        AssetEvidence.asset_id == a.id,
        AssetEvidence.key == payload.key,
        AssetEvidence.superseded_at.is_(None),
    ).update({AssetEvidence.superseded_at: now}, synchronize_session=False)
    e = AssetEvidence(
        asset_id=a.id,
        **payload.model_dump(),
        attester_subject=principal["sub"],
        self_reported=is_holder,
        recorded_at=now,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.get("/assets/{asset_id}/valuation")
def get_valuation(asset_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_AUDITOR))):
    a = _get_asset(db, asset_id)
    access = _access(db, a, principal)
    if access is None or (access != FULL and "valuation" not in access):
        raise HTTPException(status_code=403, detail="valuation not shared with you")
    result = valuate(gather_inputs(current_evidence(db, a.id)))
    if access != FULL:
        # Selective disclosure: show the result, and only the inputs in shared categories.
        result["inputs"] = {k: v for k, v in result["inputs"].items() if v["category"] in access}
    return {"asset_id": a.id, "currency": a.currency, **result}


@router.get("/assets/{asset_id}/map")
def get_map(asset_id: str, db: Session = Depends(get_db),
            principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    """How this asset connects: its evidence, the project that built it, the contributions
    behind that project, and its assurance history."""
    a = _get_asset(db, asset_id)
    access = visible_assets(db, principal).get(a.id)
    if access is None:
        raise HTTPException(status_code=403, detail="not allowed to view this asset")
    return asset_map(db, a, access)


@router.post("/assets/{asset_id}/proposals", response_model=ProposalOut, status_code=201)
def propose_revaluation(
    asset_id: str,
    payload: ProposalIn,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_ATTESTER)),
):
    """Propose that an input has moved. A proposal is **not** evidence: it waits for the
    holder or an attester. This is how an agent revalues without attesting."""
    a = _get_asset(db, asset_id)
    if visible_assets(db, principal).get(a.id) is None:
        raise HTTPException(status_code=403, detail="not allowed to view this asset")
    cfg = load_value_config()
    d = cfg.inputs.get(payload.key)
    if d is not None:
        if payload.value is None:
            raise HTTPException(status_code=422, detail=f"{payload.key} needs a numeric value")
        try:
            validate_input(payload.key, payload.value)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        category = d.category
    else:
        if payload.category not in cfg.categories:
            raise HTTPException(status_code=422, detail=f"category must be one of {list(cfg.categories)}")
        category = payload.category
    agent = db.query(AgentModel).filter(AgentModel.did == principal["sub"]).first()
    p = EvidenceProposal(asset_id=a.id, proposed_by=principal["sub"], agent_id=agent.id if agent else None,
                         category=category, key=payload.key, value=payload.value,
                         source_ref=payload.source_ref, rationale=payload.rationale)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/assets/{asset_id}/proposals", response_model=list[ProposalOut])
def list_proposals(asset_id: str, status: str | None = Query(None, pattern="^(open|accepted|rejected)$"),
                   db: Session = Depends(get_db),
                   principal=Depends(require_any_role(ROLE_USER, ROLE_AGENT, ROLE_AUDITOR))):
    a = _get_asset(db, asset_id)
    if visible_assets(db, principal).get(a.id) is None:
        raise HTTPException(status_code=403, detail="not allowed to view this asset")
    q = db.query(EvidenceProposal).filter(EvidenceProposal.asset_id == a.id)
    if status:
        q = q.filter(EvidenceProposal.status == status)
    return q.order_by(EvidenceProposal.created_at).all()


@router.post("/proposals/{proposal_id}/decision", response_model=ProposalOut)
def decide_proposal(proposal_id: str, payload: ProposalDecisionIn, db: Session = Depends(get_db),
                    principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER))):
    """The holder or an attester turns a proposal into evidence, or rejects it.
    Accepting by an attester records attested evidence; by the holder, self-reported."""
    p = db.get(EvidenceProposal, proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status != "open":
        raise HTTPException(status_code=409, detail=f"proposal already {p.status}")
    a = _get_asset(db, p.asset_id)
    me = current_user_or_none(principal, db)
    is_holder = me is not None and me.id == a.holder_user_id
    is_attester = has_any_role(principal, ROLE_ATTESTER)
    if not (is_holder or is_attester):
        raise HTTPException(status_code=403, detail="only the holder or an attester decides a proposal")

    p.decided_by = principal["sub"]
    p.decided_at = utcnow()
    p.decision_note = payload.note
    if not payload.accept:
        p.status = "rejected"
        db.commit()
        db.refresh(p)
        return p

    now = utcnow()
    db.query(AssetEvidence).filter(
        AssetEvidence.asset_id == a.id, AssetEvidence.key == p.key, AssetEvidence.superseded_at.is_(None)
    ).update({AssetEvidence.superseded_at: now}, synchronize_session=False)
    e = AssetEvidence(asset_id=a.id, category=p.category, key=p.key, value=p.value,
                      evidence_ref=payload.evidence_ref or p.source_ref,
                      attester_subject=principal["sub"], self_reported=is_holder and not is_attester,
                      recorded_at=now, text=f"accepted from proposal {p.id}")
    db.add(e)
    db.flush()
    p.status = "accepted"
    p.evidence_id = e.id
    db.commit()
    db.refresh(p)
    return p


@router.put("/assets/{asset_id}/mandate")
def set_mandate(asset_id: str, payload: MandateIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """The holder's explicit, revocable delegation to the assurance agent."""
    a = _get_asset(db, asset_id)
    _require_holder(a, me)
    bad = set(payload.allowed_actions) - ACTIONS
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown actions {sorted(bad)}; allowed: {sorted(ACTIONS)}")
    a.mandate = payload.model_dump()
    db.commit()
    return effective_mandate(a, load_value_config().default_mandate)


@router.post("/assets/{asset_id}/assurance/run", response_model=RunOut)
def run(asset_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    a = _get_asset(db, asset_id)
    _require_holder(a, me)
    return run_assurance(db, a, triggered_by=me.subject or me.id, default_mandate=load_value_config().default_mandate)


@router.get("/assets/{asset_id}/assurance/runs", response_model=list[RunOut])
def list_runs(asset_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_AUDITOR))):
    a = _get_asset(db, asset_id)
    if _access(db, a, principal) != FULL:
        raise HTTPException(status_code=403, detail="only the holder and oversight roles see assurance runs")
    return db.query(AssuranceRun).filter(AssuranceRun.asset_id == a.id).order_by(AssuranceRun.created_at.desc()).all()


@router.get("/assets/{asset_id}/shares", response_model=list[ShareOut])
def list_shares(asset_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    a = _get_asset(db, asset_id)
    _require_holder(a, me)
    return db.query(AssetShare).filter(AssetShare.asset_id == a.id).all()


@router.put("/assets/{asset_id}/shares", response_model=ShareOut)
def share(asset_id: str, payload: ShareIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Selective disclosure: share chosen evidence categories (and optionally 'valuation')."""
    a = _get_asset(db, asset_id)
    _require_holder(a, me)
    allowed = set(load_value_config().categories) | {"valuation"}
    bad = set(payload.categories) - allowed
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown categories {sorted(bad)}")
    if payload.grantee_user_id == me.id or not db.get(User, payload.grantee_user_id):
        raise HTTPException(status_code=422, detail="grantee must be another existing user")
    s = db.query(AssetShare).filter(AssetShare.asset_id == a.id, AssetShare.grantee_user_id == payload.grantee_user_id).first()
    if s is None:
        s = AssetShare(asset_id=a.id, grantee_user_id=payload.grantee_user_id, categories=sorted(set(payload.categories)))
        db.add(s)
    else:
        s.categories = sorted(set(payload.categories))
    db.commit()
    db.refresh(s)
    return s


@router.delete("/assets/{asset_id}/shares/{grantee_user_id}")
def unshare(asset_id: str, grantee_user_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    a = _get_asset(db, asset_id)
    _require_holder(a, me)
    n = db.query(AssetShare).filter(AssetShare.asset_id == a.id, AssetShare.grantee_user_id == grantee_user_id).delete()
    db.commit()
    return {"revoked": n}
