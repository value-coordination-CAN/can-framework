# CAN — For Developers

The reference backend is a FastAPI service in [`backend/`](https://github.com/value-coordination-CAN/can-framework/tree/main/backend). It records contribution, reliability and care signals, turns them into an explainable priority score, and handles allocation requests, reviewer decisions and appeals.

It is a reference implementation for pilots and research, not a production system.

---

## Auth model

- **DID-first sign-in:** `did:key` (Ed25519) challenge and response issues a short-lived CAN session token. Sessions are stored and checked on every request, and `POST /auth/did/logout` revokes them.
- **OIDC (Keycloak):** for institutions and staff roles. Signing keys are cached and refreshed when the provider rotates them.
- **Modes:** `AUTH_MODE=oidc|did|hybrid`.
- **Profiles are bound to the identity.** `POST /identity/users` creates one profile per authenticated identity. From then on the API acts on the caller's own record, and requests never choose whose record to change.

### Roles

| Role | Can do |
| --- | --- |
| `can_user` | Manage their own profile, record self-reported entries, see their own record and score, submit requests, appeal, manage care consent |
| `can_attester` | Record entries about other people. Evidence (`evidence_ref`) is required |
| `can_reviewer` | See the allocation queue, decide requests (not their own), resolve appeals (not their own, and not on requests they decided) |
| `can_admin` | Reviewer rights |
| `can_auditor` | Read-only oversight of records, requests and appeals |

DID logins receive `can_user`. Other roles come from the OIDC provider.

---

## Local dev

```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs  
Keycloak: http://localhost:8080 (admin/admin). Test users: `testuser` and `testreviewer`, both with password `testpass`.

Outside `ENV=dev`/`test`, the API **refuses to start** unless `CAN_JWT_SECRET` and `EXTERNAL_ID_PEPPER` are random values of at least 32 characters:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Tests

```bash
cd backend
pip install -r requirements.txt
pytest -q tests
```

The suite uses in-memory SQLite and the real DID login flow. It covers authentication, authorisation boundaries, scoring, care consent, decisions, appeals and the network features.

---

## Ledgers and scoring

Ledger definitions live in [`ledgers/`](https://github.com/value-coordination-CAN/can-framework/tree/main/ledgers) and are loaded and validated at startup. Weights must sum to 1.

| File | Defines |
| --- | --- |
| `contribution.yaml` | Metrics and weights: peer validation, usage impact, time commitment, outcome quality |
| `reliability.yaml` | Metrics and weights: attendance, completion rate, responsiveness, compliance |
| `care.yaml` | Care factors, weights and which factors need explicit consent (`opt_in_required`) |
| `scoring.yaml` | How ledgers combine, the care uplift, and the weight given to self-reported entries |

How a score is built:

1. Every value is normalised to **0..1**, and only metrics listed in the YAML are accepted.
2. A metric's score is the mean of its counted entries. A ledger's score is the weighted sum over **all** its metrics, and a metric with no entries counts as 0, so one extreme entry cannot dominate.
3. **Self-reported entries are kept in the person's record but do not count** towards priority by default. Attested entries with evidence do.
4. `overall = 0.5 × contribution + 0.5 × reliability + 0.2 × care`. **Care is an uplift only**: it can raise priority, never lower it.
5. Every score returns an **explanation**: the formula, each metric's weight, mean and count, and what was excluded and why. It is stored with each allocation request so the person can see exactly what their priority rested on.

---

## Care factors are opt-in

Health, parenting, burnout, age and crisis are sensitive data. Each one needs the person's explicit consent:

- `GET /identity/me/care-consent` shows what is available and what has been consented to.
- `PUT /identity/me/care-consent {"factors": ["health"]}` sets the complete consented set.
- Entries for a factor are rejected until the person has consented to it.
- Removing a factor revokes consent and **deletes** that factor's entries.
- Not consenting never lowers anyone's priority.

---

## Core APIs

| Method | Path | Who |
| --- | --- | --- |
| GET | `/auth/did/challenge` | anyone |
| POST | `/auth/did/verify`, `/auth/did/logout` | anyone / DID session |
| POST | `/identity/users` | any authenticated identity (one profile each) |
| GET | `/identity/users/me`, `/identity/users/{id}` | user (others' emails are hidden) |
| GET/PUT | `/identity/me/care-consent` | user |
| POST | `/ledger/entries` | user (self) / attester (others, with evidence) |
| GET | `/ledger/entries/{user_id}` | owner, reviewer, auditor |
| GET | `/score/{user_id}` | owner, reviewer, auditor |
| POST | `/allocation/requests` | user |
| GET | `/allocation/requests` | reviewer, auditor (queue ordered by priority) |
| GET | `/allocation/requests/{id}` | owner, reviewer, auditor (with score explanation) |
| POST | `/allocation/requests/{id}/decision` | reviewer |
| POST | `/appeals/` | owner of the request |
| GET | `/appeals/`, `/appeals/{id}` | reviewer and auditor; owner for their own |
| POST | `/appeals/{id}/resolve` | an independent reviewer |
| POST/DELETE | `/integrations/linkedin/import` | user |
| GET | `/network/path` | user (from themselves) |

See [Safeguards in the Reference Implementation](SAFEGUARDS_IN_CODE.md) for how these map onto CAN's rights and principles.
