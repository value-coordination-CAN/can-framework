from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models import LedgerEntry, ScoreSnapshot

W_CONTRIB = 0.4
W_RELIAB = 0.4
W_CARE = 0.2

def _avg_for(db: Session, user_id: str, ledger_type: str) -> float:
    val = db.query(func.avg(LedgerEntry.value)).filter(
        LedgerEntry.user_id == user_id,
        LedgerEntry.ledger_type == ledger_type,
    ).scalar()
    return float(val or 0.0)

def calculate_and_store(db: Session, user_id: str) -> ScoreSnapshot:
    c = _avg_for(db, user_id, "contribution")
    r = _avg_for(db, user_id, "reliability")
    care = _avg_for(db, user_id, "care")
    overall = round((c * W_CONTRIB) + (r * W_RELIAB) + (care * W_CARE), 6)

    snap = ScoreSnapshot(
        user_id=user_id,
        contribution_score=c,
        reliability_score=r,
        care_score=care,
        overall_score=overall,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap
