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
from app.db.models import AllocationRequest, ScoreSnapshot, User
from app.db.session import get_db
from app.schemas.allocation import (
    AllocationDecisionIn,
    AllocationRequestCreate,
    AllocationRequestDetail,
    AllocationRequestOut,
)
from app.services.allocation import create_request, decide_request

router = APIRouter()


@router.post("/requests", response_model=AllocationRequestOut)
def submit(payload: AllocationRequestCreate, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return create_request(db, me.id, payload.pool, payload.description)


@router.get("/requests", response_model=list[AllocationRequestOut])
def list_requests(
    status: str | None = Query(None, pattern="^(submitted|approved|declined|reopened)$"),
    pool: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR)),
):
    q = db.query(AllocationRequest)
    if status:
        q = q.filter(AllocationRequest.status == status)
    if pool:
        q = q.filter(AllocationRequest.pool == pool)
    return q.order_by(AllocationRequest.priority_score.desc(), AllocationRequest.created_at).all()


@router.get("/requests/{request_id}", response_model=AllocationRequestDetail)
def get_request(request_id: str, db: Session = Depends(get_db), principal=Depends(require_roles(ROLE_USER))):
    req = db.get(AllocationRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="allocation request not found")
    if not can_view_user(principal, current_user_or_none(principal, db), req.user_id):
        raise HTTPException(status_code=403, detail="not allowed to view this request")
    snap = db.get(ScoreSnapshot, req.score_snapshot_id) if req.score_snapshot_id else None
    out = AllocationRequestDetail.model_validate(req)
    out.score_explanation = snap.explanation if snap else None
    return out


@router.post("/requests/{request_id}/decision", response_model=AllocationRequestOut)
def decide(
    request_id: str,
    payload: AllocationDecisionIn,
    db: Session = Depends(get_db),
    principal=Depends(require_any_role(ROLE_REVIEWER, ROLE_ADMIN)),
):
    req = db.get(AllocationRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="allocation request not found")
    me = current_user_or_none(principal, db)
    if me is not None and me.id == req.user_id:
        raise HTTPException(status_code=403, detail="reviewers cannot decide their own requests")
    return decide_request(db, req, payload.decision, payload.reason, principal["sub"])
