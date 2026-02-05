from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.schemas.ledgers import LedgerEntryCreate, LedgerEntryOut
from app.services.ledger import create_ledger_entry
from app.core.auth import require_roles

router = APIRouter()

@router.post("/entries", response_model=LedgerEntryOut)
def add_entry(payload: LedgerEntryCreate, db: Session = Depends(get_db), principal=Depends(require_roles("can_user"))):
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="user not found")
    e = create_ledger_entry(
        db,
        user_id=payload.user_id,
        ledger_type=payload.ledger_type,
        metric=payload.metric,
        value=payload.value,
        evidence_ref=payload.evidence_ref,
    )
    return e
