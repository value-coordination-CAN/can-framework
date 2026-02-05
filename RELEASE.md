# Release Checklist (CAN)

## 1. Versioning
- Update version references (e.g., `CITATION.cff`, docs, changelog)
- Choose semantic version: `MAJOR.MINOR.PATCH`

## 2. Security and Compliance
- Confirm no secrets in repo (`.env`, keys, credentials)
- Run dependency audit (e.g., `pip-audit` or equivalent)
- Verify auth flows (OIDC + DID) still pass tests

## 3. Quality Gates
- CI passing on `main`
- Unit tests and minimal integration tests passing

## 4. Documentation
- Update `README.md` with release notes highlights
- Update `about/*` pages if interfaces changed
- Add or update migration notes (Alembic)

## 5. Tag and Publish
```bash
git checkout main
git pull

git tag -a vX.Y.Z -m "CAN vX.Y.Z"
git push origin vX.Y.Z
```
