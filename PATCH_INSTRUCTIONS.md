# CAN LinkedIn Import + 6+ Degrees (Integration Pack)
**Date:** 2026-02-06

## Copy files into your repo
Copy folders from this ZIP into your repo root:

- `docs/`
- `backend/`

## Backend wiring (FastAPI)
Include routers (example in your `backend/app/main.py`):

```python
from app.routers.linkedin_integration import router as linkedin_router
from app.routers.network_paths import router as network_router

app.include_router(linkedin_router, prefix="/integrations/linkedin", tags=["integrations"])
app.include_router(network_router, prefix="/network", tags=["network"])
```

## Database migration
A sample Alembic migration is provided:
`backend/alembic/versions/016f621224c7_linkedin_network_edges.py`

Run:
```bash
cd backend
alembic upgrade head
```

## Docs menu
Use `docs/integrations/LINKEDIN_MENU_SNIPPET.md` to add links to your homepage without replacing your current menu.
