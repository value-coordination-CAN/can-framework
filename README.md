# Contribution–Access Network (CAN)
## Open Coordination Infrastructure

**Repo:** https://github.com/value-coordination-CAN/can-framework  
**Docs:** https://value-coordination-CAN.github.io/can-framework/

CAN is an open framework for allocating access to shared resources using verified **contribution**, **reliability**, and **care** signals.

It is designed as a **parallel coordination layer** that can complement monetary systems and strengthen allocative accuracy, social resilience, and institutional legitimacy in digitally mediated economies — acting as a bridge toward **direct value handling**, while remaining compatible with existing monetary and regulatory systems.

---

## 📘 Documentation

- Overview: `docs/index.md`
- Policy overview: `about/POLICY_ABOUT.md`
- For Regulators: `about/FOR_REGULATORS.md`
- For Universities & Research: `about/FOR_UNIVERSITIES_AND_RESEARCH.md`
- For Developers: `about/FOR_DEVELOPERS.md`

---

## 🚀 Reference Backend (OIDC + DID-first)

See `backend/` for a FastAPI reference implementation:

- Keycloak OIDC integration
- DID-first sign-in (`did:key` Ed25519) issuing CAN session tokens
- Hybrid mode: `AUTH_MODE=oidc|did|hybrid`
- Ledger, scoring, allocation, and appeals APIs
- Persisted DID challenges/sessions, assurance levels, DID↔OIDC subject linking

Quickstart:
```bash
cd backend
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs  
Keycloak: http://localhost:8080 (admin/admin)

---

## 🏛 Governance

- Governance: `GOVERNANCE.md`
- Contributing: `CONTRIBUTING.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`
- Security: `SECURITY.md`
- Releases: `RELEASE.md`
