from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import AllocationRequest
from app.services.scoring import calculate_and_store

DECISIONS = {"approved", "declined"}


def create_request(db: Session, user_id: str, pool: str, description: str) -> AllocationRequest:
    snap = calculate_and_store(db, user_id)
    req = AllocationRequest(
        user_id=user_id,
        pool=pool,
        description=description,
        status="submitted",
        priority_score=snap.overall_score,
        score_snapshot_id=snap.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def decide_request(db: Session, req: AllocationRequest, decision: str, reason: str, reviewer_subject: str) -> AllocationRequest:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    req.status = decision
    req.decision_reason = reason
    req.decided_by = reviewer_subject
    req.decided_at = utcnow()
    db.commit()
    db.refresh(req)
    return req
