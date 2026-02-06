# LinkedIn Import + Multi-Degree Paths

Adds:
- POST `/integrations/linkedin/import` (CSV)
- GET `/network/path` (max_depth supports > 3)

## Wiring
Include routers into your FastAPI app:
- `app.routers.linkedin_integration`
- `app.routers.network_paths`

## Privacy
- Store only hashed external identifiers (li:sha256)
- Do not crawl LinkedIn
- Provide delete endpoint later (recommended)
