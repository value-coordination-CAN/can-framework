from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.services.linkedin_importer import import_linkedin_connections

router = APIRouter()

MAX_CSV_BYTES = 5 * 1024 * 1024


@router.post("/import")
async def import_connections(
    file: UploadFile = File(...),
    replace: bool = Form(False),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Import your own LinkedIn connections export. Only a keyed hash of each connection is stored."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file")
    content = await file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV too large (max 5 MB)")
    return import_linkedin_connections(
        db=db,
        user_id=me.id,
        csv_bytes=content,
        replace=replace,
        source_filename=file.filename,
    )


@router.delete("/import")
def delete_imported(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    """Delete every connection you imported from LinkedIn."""
    from app.models.network_edge import NetworkEdge

    n = db.query(NetworkEdge).filter(
        NetworkEdge.source_user_id == me.id,
        NetworkEdge.source_system == "linkedin_export",
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted": n}
