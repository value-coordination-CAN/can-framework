# backend/app/main.py

from fastapi import FastAPI
from app.api.router import router

app = FastAPI()
app.include_router(router)

# Optional: LinkedIn integration (do not break app if missing deps/modules)
try:
    from app.routers.linkedin_integration import router as linkedin_router
    app.include_router(linkedin_router, prefix="/linkedin", tags=["linkedin"])
except ModuleNotFoundError:
    # LinkedIn integration not installed/available in this build
    pass