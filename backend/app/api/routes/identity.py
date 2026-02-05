from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.schemas.identity import UserCreate, UserOut
from app.core.auth import require_roles

router = APIRouter()

@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), principal=Depends(require_roles("can_user"))):
    if db.query(User).filter(User.email == str(payload.email)).first():
        raise HTTPException(status_code=409, detail="email already exists")
    u = User(display_name=payload.display_name, email=str(payload.email))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db), principal=Depends(require_roles("can_user"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    return u
