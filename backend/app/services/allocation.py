from sqlalchemy.orm import Session
from app.db.models import AllocationRequest
from app.services.scoring import calculate_and_store

def create_request(db: Session, user_id: str, pool: str, description: str) -> AllocationRequest:
    snap = calculate_and_store(db, user_id)
    req = AllocationRequest(
        user_id=user_id,
        pool=pool,
        description=description,
        status="submitted",
        priority_score=snap.overall_score,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req
