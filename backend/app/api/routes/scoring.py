from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import ROLE_USER, can_view_user, current_user_or_none, require_roles
from app.db.models import User
from app.db.session import get_db
from app.schemas.scoring import ScoreOut
from app.services.scoring import calculate_and_store, compute_score

router = APIRouter()


def _authorise(user_id: str, principal: dict, db: Session) -> None:
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="user not found")
    if not can_view_user(principal, current_user_or_none(principal, db), user_id):
        raise HTTPException(status_code=403, detail="not allowed to view this score")


@router.get("/{user_id}", response_model=ScoreOut)
def preview(user_id: str, db: Session = Depends(get_db), principal=Depends(require_roles(ROLE_USER))):
    """Current score with its full explanation, without storing a snapshot."""
    _authorise(user_id, principal, db)
    return ScoreOut(user_id=user_id, **compute_score(db, user_id))


@router.post("/calculate/{user_id}", response_model=ScoreOut)
def calculate(user_id: str, db: Session = Depends(get_db), principal=Depends(require_roles(ROLE_USER))):
    _authorise(user_id, principal, db)
    snap = calculate_and_store(db, user_id)
    return ScoreOut(
        user_id=user_id,
        contribution_score=snap.contribution_score,
        reliability_score=snap.reliability_score,
        care_score=snap.care_score,
        overall_score=snap.overall_score,
        explanation=snap.explanation or {},
    )
