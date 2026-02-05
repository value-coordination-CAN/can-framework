from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.schemas.scoring import ScoreOut
from app.services.scoring import calculate_and_store
from app.core.auth import require_roles

router = APIRouter()

@router.post("/calculate/{user_id}", response_model=ScoreOut)
def calculate(user_id: str, db: Session = Depends(get_db), principal=Depends(require_roles("can_user"))):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="user not found")
    snap = calculate_and_store(db, user_id)
    return ScoreOut(
        user_id=user_id,
        contribution_score=snap.contribution_score,
        reliability_score=snap.reliability_score,
        care_score=snap.care_score,
        overall_score=snap.overall_score,
    )
