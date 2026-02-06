from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.auth import get_current_user  # adapt
from app.services.network_graph import find_paths

router = APIRouter()

@router.get("/path")
def get_path(
    to: str = Query(..., description="Target CAN user_id or external_id"),
    from_user: str | None = Query(None, alias="from"),
    max_depth: int = Query(6, ge=1, le=12),
    top_n: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    src = from_user or str(current_user.id)
    return find_paths(db=db, source_id=src, target_id=to, max_depth=max_depth, top_n=top_n)
