# Production Upgrades (DID-first + OIDC)

This backend supports:
- OIDC tokens from Keycloak
- DID-first login via `did:key` (Ed25519) producing CAN session JWTs

Included:
- Persisted DID challenges (`did_challenges`)
- Persisted DID sessions (`did_sessions`) suitable for audit & revocation
- Assurance levels (A1 default; upgrade paths for VC/did:web)
- DID ↔ OIDC subject linking (`subject_links`)

Next (recommended):
- Add revocation endpoint and DB checks for revoked sessions
- Add OIDC user → DID linking flow (`/auth/did/link/*`)
- Add rate limiting (Redis) to auth endpoints
