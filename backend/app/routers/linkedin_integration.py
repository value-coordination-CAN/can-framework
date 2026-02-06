from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.auth import get_current_user  # adapt to your project
from app.services.linkedin_importer import import_linkedin_connections

router = APIRouter()

@router.post("/import")
async def import_connections(
    file: UploadFile = File(...),
    replace: bool = Form(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file")
    content = await file.read()
    return import_linkedin_connections(
        db=db,
        user_id=str(current_user.id),
        csv_bytes=content,
        replace=replace,
        source_filename=file.filename,
    )
