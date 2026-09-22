# backend/app/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router
from app.core.config import validate_settings
from app.routers.linkedin_integration import router as linkedin_router
from app.routers.network_paths import router as network_router
from app.services.ledger_config import load_ledger_config


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_settings()
    load_ledger_config()  # fail fast on invalid ledger YAML
    yield


app = FastAPI(title="CAN Backend", lifespan=lifespan)
app.include_router(router)
app.include_router(linkedin_router, prefix="/integrations/linkedin", tags=["linkedin"])
app.include_router(network_router, prefix="/network", tags=["network"])
