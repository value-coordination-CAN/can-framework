# CAN Backend (Reference Implementation)

Starter backend for the Contribution–Access Network (CAN).

## Features
- Keycloak OIDC integration (enterprise-friendly)
- DID-first auth (`did:key` Ed25519) issuing CAN session JWTs, with logout and revocation
- Hybrid auth mode: accept OIDC or DID-session tokens (`AUTH_MODE=oidc|did|hybrid`)
- Ledger API (contribution/reliability/care), bound to the authenticated person
- Explainable scoring driven by the YAML in [`../ledgers`](../ledgers)
- Allocation requests with reviewer decisions, and appeals with independent resolution
- Opt-in, revocable consent for sensitive care factors
- LinkedIn connections import (keyed hashes only) and multi-degree network paths

## Quickstart (Dev)
```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs  
Keycloak: http://localhost:8080 (admin/admin)

Outside `ENV=dev`/`test` the API refuses to start unless `CAN_JWT_SECRET` and
`EXTERNAL_ID_PEPPER` are random values of at least 32 characters. Change the Keycloak
client secret (`dev-secret-change-me`) and the test users before any real deployment.

## Roles

| Role | Can do |
| --- | --- |
| `can_user` | Create and read their own profile, record self-reported entries, see their own record and score, submit allocation requests, appeal their own decisions, manage care consent |
| `can_attester` | Record ledger entries about other people. `evidence_ref` is required |
| `can_reviewer` | See the allocation queue, decide requests (not their own), resolve appeals (not their own, and not on requests they decided) |
| `can_admin` | Reviewer rights |
| `can_auditor` | Read-only access to records, requests and appeals |

DID logins receive `can_user`. Other roles come from the OIDC provider.

## How scoring works

- Ledger values are normalised to **0..1**. Metrics must be listed in the ledger YAML.
- A metric's score is the mean of its counted entries. A ledger's score is the YAML-weighted
  sum over **all** its metrics, and a metric with no entries counts as 0, so one high entry
  cannot dominate.
- **Self-reported entries do not count** towards priority by default
  (`self_reported_weight: 0` in `ledgers/scoring.yaml`). Only attested entries with
  evidence do.
- `overall = 0.5 × contribution + 0.5 × reliability + 0.2 × care`. **Care is an uplift
  only**: it can raise priority but never lower it.
- Every score carries an `explanation` (formula, per-metric weights, means, counts and
  exclusions). The person can read it at `GET /score/{user_id}` and on their allocation
  request, and can contest it by appeal.

## Care factors are opt-in

Every care factor (health, parenting, burnout, age, crisis) is sensitive and is listed under
`opt_in_required` in `ledgers/care.yaml`.

- Nothing can be recorded for a factor until the person consents with
  `PUT /identity/me/care-consent {"factors": ["health"]}`.
- The PUT sets the complete consented set. Removing a factor revokes consent and
  **deletes** that factor's entries.
- Not consenting never lowers anyone's priority.

## Main endpoints

| Method | Path | Who |
| --- | --- | --- |
| POST | `/identity/users` | any authenticated identity (one profile each) |
| GET | `/identity/users/me` | user |
| GET/PUT | `/identity/me/care-consent` | user |
| POST | `/ledger/entries` | user (self) / attester (others, with evidence) |
| GET | `/ledger/entries/{user_id}` | owner, reviewer, auditor |
| GET | `/score/{user_id}` | owner, reviewer, auditor |
| POST | `/allocation/requests` | user |
| GET | `/allocation/requests` | reviewer, auditor |
| GET | `/allocation/requests/{id}` | owner, reviewer, auditor (includes the score explanation) |
| POST | `/allocation/requests/{id}/decision` | reviewer |
| POST | `/appeals/` | owner of the request |
| GET | `/appeals/`, `/appeals/{id}` | reviewer/auditor; owner for their own |
| POST | `/appeals/{id}/resolve` | a reviewer other than the appellant and the original decision-maker |
| POST | `/auth/did/logout` | DID session |

## OIDC test users
Realm import creates:
- `testuser` / `testpass` (`can_user`)
- `testreviewer` / `testpass` (`can_user`, `can_attester`, `can_reviewer`)

Token (example):
```bash
curl -s http://localhost:8080/realms/can/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id=can-api" \
  -d "client_secret=dev-secret-change-me" \
  -d "username=testuser" \
  -d "password=testpass"
```

## Tests
```bash
pip install -r requirements.txt
pytest -q tests
```
The tests use an in-memory SQLite database and the real DID login flow.
