# LinkedIn Import + Multi-Degree Paths

Endpoints (mounted in `app/main.py`):
- POST `/integrations/linkedin/import`: upload your own LinkedIn connections export (CSV, max 5 MB)
- DELETE `/integrations/linkedin/import`: delete everything you imported
- GET `/network/path?to=...`: multi-degree paths from yourself (`max_depth` up to 12).
  Reviewers may pass `from=`.

## Privacy
- Your connections have not consented to CAN, so their names and emails are **not stored**.
- Each connection is stored only as a keyed hash of their profile URL (or email):
  `li:HMAC-SHA256(EXTERNAL_ID_PEPPER, value)`. Without the server-side pepper, the ids
  cannot be reversed by hashing guessed emails. Keep `EXTERNAL_ID_PEPPER` secret and stable.
- No LinkedIn crawling or API access.

## Path confidence
`confidence = product of edge weights × 0.6^(hops − 1)`. The search runs breadth-first, one
query per depth level, and returns alternative routes of the same length, not only the first
one found.
