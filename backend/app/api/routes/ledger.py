from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import (
    ROLE_ADMIN,
    ROLE_ATTESTER,
    ROLE_AUDITOR,
    ROLE_REVIEWER,
    ROLE_USER,
    can_view_user,
    current_user_or_none,
    get_current_user,
    has_any_role,
    require_any_role,
)
from app.db.models import EntryDispute, LedgerEntry, User
from app.db.session import get_db
from app.schemas.ledgers import DisputeCreate, DisputeOut, DisputeResolveIn, LedgerEntryCreate, LedgerEntryOut
from app.services.corrections import (
    CorrectionError,
    CorrectionForbidden,
    delete_self_reported,
    open_dispute,
    resolve_dispute,
)
from app.services.ledger import ConsentRequiredError, LedgerValidationError, create_ledger_entry

router = APIRouter()


@router.post("/entries", response_model=LedgerEntryOut)
def add_entry(
    payload: LedgerEntryCreate,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER)),
):
    """Record an entry about yourself (self-reported, does not count towards priority by default)
    or, with can_attester, about someone else (evidence required)."""
    me = current_user_or_none(principal, db)
    target_id = payload.user_id or (me.id if me else None)
    if target_id is None:
        raise HTTPException(status_code=422, detail="user_id is required when you have no CAN profile")
    if not db.get(User, target_id):
        raise HTTPException(status_code=404, detail="user not found")

    self_reported = me is not None and me.id == target_id
    if not self_reported:
        if not has_any_role(principal, ROLE_ATTESTER):
            raise HTTPException(status_code=403, detail="recording entries about others requires can_attester")
        if not payload.evidence_ref:
            raise HTTPException(status_code=422, detail="evidence_ref is required for attested entries")

    try:
        return create_ledger_entry(
            db,
            user_id=target_id,
            ledger_type=payload.ledger_type,
            metric=payload.metric,
            value=payload.value,
            evidence_ref=payload.evidence_ref,
            attester_subject=principal["sub"],
            self_reported=self_reported,
        )
    except LedgerValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ConsentRequiredError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Delete one of your own self-reported entries. Attested entries are disputed instead."""
    entry = db.get(LedgerEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="entry not found")
    try:
        delete_self_reported(db, entry, me)
    except CorrectionForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CorrectionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"deleted": entry_id}


@router.post("/entries/{entry_id}/disputes", response_model=DisputeOut)
def dispute_entry(entry_id: str, payload: DisputeCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Right to correction: dispute an attested entry about you. It keeps counting until resolved."""
    entry = db.get(LedgerEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="entry not found")
    try:
        return open_dispute(db, entry, me, payload.reason, payload.proposed_value)
    except CorrectionForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CorrectionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/disputes", response_model=list[DisputeOut])
def list_disputes(
    status: str | None = Query("open", pattern="^(open|corrected|removed|rejected)$"),
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR)),
):
    q = db.query(EntryDispute)
    if status:
        q = q.filter(EntryDispute.status == status)
    return q.order_by(EntryDispute.created_at).all()


@router.get("/disputes/{dispute_id}", response_model=DisputeOut)
def get_dispute(dispute_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER))):
    d = db.get(EntryDispute, dispute_id)
    if not d:
        raise HTTPException(status_code=404, detail="dispute not found")
    if not can_view_user(principal, current_user_or_none(principal, db), d.user_id):
        raise HTTPException(status_code=403, detail="not allowed to view this dispute")
    return d


@router.post("/disputes/{dispute_id}/resolve", response_model=DisputeOut)
def resolve(
    dispute_id: str,
    payload: DisputeResolveIn,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_REVIEWER, ROLE_ADMIN)),
):
    d = db.get(EntryDispute, dispute_id)
    if not d:
        raise HTTPException(status_code=404, detail="dispute not found")
    me = current_user_or_none(principal, db)
    try:
        return resolve_dispute(
            db,
            d,
            outcome=payload.outcome,
            note=payload.note,
            corrected_value=payload.corrected_value,
            reviewer_subject=principal["sub"],
            reviewer_user_id=me.id if me else None,
        )
    except CorrectionForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CorrectionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/entries/{user_id}", response_model=list[LedgerEntryOut])
def list_entries(user_id: str, db: Session = Depends(get_db), principal=Depends(require_any_role(ROLE_USER, ROLE_ATTESTER))):
    """The person holds their record: owners (and reviewers/auditors) can see every entry about them."""
    if not can_view_user(principal, current_user_or_none(principal, db), user_id):
        raise HTTPException(status_code=403, detail="not allowed to view this record")
    return (
        db.query(LedgerEntry)
        .filter(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.created_at)
        .all()
    )
