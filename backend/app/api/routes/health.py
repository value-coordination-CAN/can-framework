from fastapi import APIRouter
from app.schemas.common import APIMessage

router = APIRouter()

@router.get("/health", response_model=APIMessage)
def health():
    return {"message": "ok"}
