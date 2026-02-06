from fastapi import FastAPI
from app.core.config import settings
from app.api.router import router

app = FastAPI(title=settings.APP_NAME)
app.include_router(router)
```python
from app.routers.linkedin_integration import router as linkedin_router
from app.routers.network_paths import router as network_router

app.include_router(linkedin_router, prefix="/integrations/linkedin", tags=["integrations"])
app.include_router(network_router, prefix="/network", tags=["network"])
```
