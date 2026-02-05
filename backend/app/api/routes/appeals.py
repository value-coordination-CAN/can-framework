from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Appeal, AllocationRequest, User
from app.schemas.appeals import AppealCreate, AppealOut
from app.core.auth import require_roles

router = APIRouter()

@router.post("/", response_model=AppealOut)
def create(payload: AppealCreate, db: Session = Depends(get_db), principal=Depends(require_roles("can_user"))):
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="user not found")
    if not db.get(AllocationRequest, payload.request_id):
        raise HTTPException(status_code=404, detail="allocation request not found")

    a = Appeal(user_id=payload.user_id, request_id=payload.request_id, reason=payload.reason)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a
