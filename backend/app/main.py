# backend/app/main.py

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.core.config import validate_settings
from app.routers.linkedin_integration import router as linkedin_router
from app.routers.network_paths import router as network_router
from app.services.ledger_config import load_ledger_config
from app.agents.config import load_agent_rules
from app.agents.routes import router as agents_router
from app.bridge.routes import router as bridge_router
from app.value.engine import load_value_config
from app.value.routes import router as value_router

UI_DIR = Path(__file__).resolve().parent / "ui"


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_settings()
    load_ledger_config()  # fail fast on invalid ledger YAML
    load_value_config()
    load_agent_rules()
    yield


app = FastAPI(title="CAN Backend", lifespan=lifespan)
app.include_router(router)
app.include_router(linkedin_router, prefix="/integrations/linkedin", tags=["linkedin"])
app.include_router(network_router, prefix="/network", tags=["network"])
app.include_router(value_router, prefix="/value", tags=["value-assurance (WP-011)"])
app.include_router(bridge_router, prefix="/bridge", tags=["bridge-wallet (WP-010)"])
app.include_router(agents_router, prefix="/agents", tags=["agent participation"])

# Reference UI (static, no build step): http://localhost:8000/ui/
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/")
