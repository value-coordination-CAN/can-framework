from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import ROLE_USER, can_view_user, current_user_or_none, get_current_user, require_roles
from app.db.models import User
from app.db.session import get_db
from app.schemas.identity import CareConsentIn, CareConsentOut, UserCreate, UserOut, UserPublicOut
from app.services.care_consent import active_consented_factors, set_care_consent
from app.services.ledger_config import load_ledger_config

router = APIRouter()


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), principal=Depends(require_roles(ROLE_USER))):
    """Create the CAN profile for the authenticated identity. One profile per identity."""
    if db.query(User).filter(User.subject == principal["sub"]).first():
        raise HTTPException(status_code=409, detail="this identity already has a CAN profile")
    if db.query(User).filter(User.email == str(payload.email)).first():
        raise HTTPException(status_code=409, detail="email already exists")
    u = User(display_name=payload.display_name, email=str(payload.email), subject=principal["sub"])
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.get("/users/me", response_model=UserOut)
def get_me(me: User = Depends(get_current_user)):
    return me


@router.get("/users/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db), principal=Depends(require_roles(ROLE_USER))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    if can_view_user(principal, current_user_or_none(principal, db), user_id):
        return UserOut.model_validate(u)
    return UserPublicOut.model_validate(u)


def _consent_out(db: Session, user_id: str, **extra) -> CareConsentOut:
    care = load_ledger_config().ledgers["care"]
    return CareConsentOut(
        consented_factors=sorted(active_consented_factors(db, user_id)),
        available_factors=sorted(care.opt_in_required),
        **extra,
    )


@router.get("/me/care-consent", response_model=CareConsentOut)
def get_care_consent(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return _consent_out(db, me.id)


@router.put("/me/care-consent", response_model=CareConsentOut)
def put_care_consent(payload: CareConsentIn, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Set exactly which sensitive care factors may be recorded and counted. Revoking deletes that factor's entries."""
    try:
        result = set_care_consent(db, me.id, set(payload.factors))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _consent_out(
        db,
        me.id,
        granted=result["granted"],
        revoked=result["revoked"],
        entries_deleted=result["entries_deleted"],
    )
