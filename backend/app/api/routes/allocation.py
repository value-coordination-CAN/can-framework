from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.schemas.allocation import AllocationRequestCreate, AllocationRequestOut
from app.services.allocation import create_request
from app.core.auth import require_roles

router = APIRouter()

@router.post("/requests", response_model=AllocationRequestOut)
def submit(payload: AllocationRequestCreate, db: Session = Depends(get_db), principal=Depends(require_roles("can_user"))):
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="user not found")
    req = create_request(db, payload.user_id, payload.pool, payload.description)
    return req
