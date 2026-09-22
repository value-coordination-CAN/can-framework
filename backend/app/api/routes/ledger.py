from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import (
    ROLE_ATTESTER,
    ROLE_USER,
    can_view_user,
    current_user_or_none,
    has_any_role,
    require_any_role,
)
from app.db.models import LedgerEntry, User
from app.db.session import get_db
from app.schemas.ledgers import LedgerEntryCreate, LedgerEntryOut
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
