from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_principal, get_current_user, is_reviewer
from app.db.models import User
from app.db.session import get_db
from app.services.network_graph import find_paths

router = APIRouter()


@router.get("/path")
def get_path(
    to: str = Query(..., description="Target CAN user_id or external id (li:...)"),
    from_user: str | None = Query(None, alias="from"),
    max_depth: int = Query(6, ge=1, le=12),
    top_n: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
    principal=Depends(get_current_principal),
):
    src = from_user or me.id
    if src != me.id and not is_reviewer(principal):
        raise HTTPException(status_code=403, detail="you can only search paths from yourself")
    return find_paths(db=db, source_id=src, target_id=to, max_depth=max_depth, top_n=top_n)
