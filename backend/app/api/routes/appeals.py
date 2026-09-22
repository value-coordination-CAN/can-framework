from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_REVIEWER,
    ROLE_USER,
    can_view_user,
    current_user_or_none,
    get_current_user,
    require_any_role,
    require_roles,
)
from app.core.time import utcnow
from app.db.models import AllocationRequest, Appeal, User
from app.db.session import get_db
from app.schemas.appeals import AppealCreate, AppealOut, AppealResolveIn

router = APIRouter()


@router.post("/", response_model=AppealOut)
def create(payload: AppealCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    req = db.get(AllocationRequest, payload.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="allocation request not found")
    if req.user_id != me.id:
        raise HTTPException(status_code=403, detail="you can only appeal your own requests")
    if db.query(Appeal).filter(Appeal.request_id == req.id, Appeal.status == "open").first():
        raise HTTPException(status_code=409, detail="an appeal for this request is already open")

    a = Appeal(user_id=me.id, request_id=req.id, reason=payload.reason)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.get("/", response_model=list[AppealOut])
def list_appeals(
    status: str | None = Query("open", pattern="^(open|upheld|rejected)$"),
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR)),
):
    q = db.query(Appeal)
    if status:
        q = q.filter(Appeal.status == status)
    return q.order_by(Appeal.created_at).all()


@router.get("/{appeal_id}", response_model=AppealOut)
def get_appeal(appeal_id: str, db: Session = Depends(get_db), principal=Depends(require_roles(ROLE_USER))):
    a = db.get(Appeal, appeal_id)
    if not a:
        raise HTTPException(status_code=404, detail="appeal not found")
    if not can_view_user(principal, current_user_or_none(principal, db), a.user_id):
        raise HTTPException(status_code=403, detail="not allowed to view this appeal")
    return a


@router.post("/{appeal_id}/resolve", response_model=AppealOut)
def resolve(
    appeal_id: str,
    payload: AppealResolveIn,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_REVIEWER, ROLE_ADMIN)),
):
    a = db.get(Appeal, appeal_id)
    if not a:
        raise HTTPException(status_code=404, detail="appeal not found")
    if a.status != "open":
        raise HTTPException(status_code=409, detail="appeal already resolved")
    me = current_user_or_none(principal, db)
    if me is not None and me.id == a.user_id:
        raise HTTPException(status_code=403, detail="reviewers cannot resolve their own appeals")

    req = db.get(AllocationRequest, a.request_id)
    if req is not None and req.decided_by == principal["sub"]:
        raise HTTPException(status_code=403, detail="an appeal must be resolved by someone other than the original decision-maker")

    a.status = payload.outcome
    a.resolution_note = payload.note
    a.resolved_by = principal["sub"]
    a.resolved_at = utcnow()
    if payload.outcome == "upheld" and req is not None:
        req.status = "reopened"  # goes back for a fresh decision
    db.commit()
    db.refresh(a)
    return a
