# Production Upgrades (DID-first + OIDC)

This backend supports:
- OIDC tokens from Keycloak (JWKS cached with a TTL and refreshed on key rotation)
- DID-first login via `did:key` (Ed25519) producing CAN session JWTs

Included:
- Persisted, single-use DID challenges (`did_challenges`)
- Persisted DID sessions (`did_sessions`), checked on every request. `POST /auth/did/logout` revokes a session
- Assurance levels (A1 default; upgrade paths for VC/did:web)
- DID ↔ OIDC subject linking (`subject_links`)
- Profiles bound to the authenticated subject (`users.subject`)
- Startup refuses default or weak secrets outside `ENV=dev`/`test`

Next (recommended):
- Add OIDC user → DID linking flow (`/auth/did/link/*`)
- Add rate limiting (Redis) to auth endpoints
- Move DID session tokens to asymmetric signing (EdDSA/ES256) if other services must verify them
- Add attester accreditation (which attesters may record which metrics)
- Add retention periods for ledger entries, snapshots and deletion records (account deletion and export are implemented)
