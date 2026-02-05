# CAN Backend (Reference Implementation)

Starter backend for the Contribution–Access Network (CAN).

## Features
- Keycloak OIDC integration (enterprise-friendly)
- DID-first auth (`did:key` Ed25519) issuing CAN session JWTs
- Hybrid auth mode: accept OIDC or DID-session tokens (`AUTH_MODE=oidc|did|hybrid`)
- Ledger API (contribution/reliability/care)
- Scoring engine (baseline)
- Allocation requests + appeals
- Production upgrades: persisted DID challenges/sessions, assurance levels, DID↔OIDC subject linking

## Quickstart (Dev)
```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs  
Keycloak: http://localhost:8080 (admin/admin)

## OIDC test user
Realm import creates:
- user: `testuser`
- pass: `testpass`

Token (example):
```bash
curl -s http://localhost:8080/realms/can/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id=can-api" \
  -d "client_secret=dev-secret-change-me" \
  -d "username=testuser" \
  -d "password=testpass"
```
