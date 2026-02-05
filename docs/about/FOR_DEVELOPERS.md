# CAN — For Developers

## Auth model
- Backend: OIDC (Keycloak)
- Frontend: DID-first sign-in (`did:key` Ed25519)
- Modes: `AUTH_MODE=oidc|did|hybrid`

## Local dev
```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs  
Keycloak: http://localhost:8080 (admin/admin)

## Core APIs (starter)
- `/identity/users`
- `/ledger/entries`
- `/score/calculate/{user_id}`
- `/allocation/requests`
- `/appeals/`
- `/auth/did/challenge` and `/auth/did/verify`
