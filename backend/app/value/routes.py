"""WP-011 Value Assurance API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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
from app.core.time import utcnow
from app.db.models import User
from app.db.session import get_db
from app.value.agent import ACTIONS, effective_mandate, run_assurance
from app.value.engine import current_evidence, gather_inputs, load_value_config, validate_input, valuate
from app.value.models import Asset, AssetEvidence, AssetShare, AssuranceRun
from app.value.schemas import (
    AssetCreate,
    AssetOut,
    EvidenceCreate,
    EvidenceOut,
    MandateIn,
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
