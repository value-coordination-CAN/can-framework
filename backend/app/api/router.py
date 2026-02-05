from fastapi import APIRouter
from app.api.routes import health, identity, ledger, scoring, allocation, appeals, did_auth

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(identity.router, prefix="/identity", tags=["identity"])
router.include_router(ledger.router, prefix="/ledger", tags=["ledger"])
router.include_router(scoring.router, prefix="/score", tags=["score"])
router.include_router(allocation.router, prefix="/allocation", tags=["allocation"])
router.include_router(appeals.router, prefix="/appeals", tags=["appeals"])
router.include_router(did_auth.router, prefix="/auth/did", tags=["auth-did"])
