from sqlalchemy.orm import Session
from app.db.models import LedgerEntry

def create_ledger_entry(db: Session, **kwargs) -> LedgerEntry:
    entry = LedgerEntry(**kwargs)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
