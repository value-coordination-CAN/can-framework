import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.did_session import verify_did_session_token
from app.core.oidc import extract_roles, verify_access_token
from app.db.models import DIDSession, User
from app.db.session import get_db

# Roles
ROLE_USER = "can_user"          # act on one's own record
ROLE_ATTESTER = "can_attester"  # record ledger entries about other people, with evidence
ROLE_REVIEWER = "can_reviewer"  # decide allocation requests and resolve appeals
ROLE_ADMIN = "can_admin"
ROLE_AUDITOR = "can_auditor"    # read-only oversight

bearer = HTTPBearer(auto_error=False)


def _did_session_active(db: Session, claims: dict) -> bool:
    s = db.get(DIDSession, claims.get("sid"))
    return (
        s is not None
        and not s.is_revoked
        and s.did == claims.get("sub")
        and int(s.expires_at) >= int(time.time())
    )


def get_current_principal(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = creds.credentials
    mode = (settings.AUTH_MODE or "hybrid").lower().strip()

    if mode in {"hybrid", "oidc"}:
        try:
            claims = verify_access_token(token, settings.OIDC_ISSUER, settings.OIDC_AUDIENCE)
            return {
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "username": claims.get("preferred_username"),
                "roles": list(extract_roles(claims)),
                "auth": "oidc",
                "claims": claims,
            }
        except Exception:
            if mode == "oidc":
                raise HTTPException(status_code=401, detail="invalid oidc token")

    if mode in {"hybrid", "did"}:
        try:
            claims = verify_did_session_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="invalid token")
        if not _did_session_active(db, claims):
            raise HTTPException(status_code=401, detail="session revoked or expired")
        return {
            "sub": claims.get("sub"),
            "sid": claims.get("sid"),
            "email": None,
            "username": None,
            "roles": claims.get("roles", []),
            "assurance": claims.get("assurance"),
            "auth": "did",
            "claims": claims,
        }

    raise HTTPException(status_code=401, detail="unauthorised")


def has_any_role(principal: dict, *roles: str) -> bool:
    return bool(set(principal.get("roles") or []) & set(roles))


def require_roles(*required: str):
    def _inner(p=Depends(get_current_principal)):
        roles = set(p["roles"] or [])
        if not set(required).issubset(roles):
            raise HTTPException(status_code=403, detail="insufficient role")
        return p
    return _inner


def require_any_role(*allowed: str):
    def _inner(p=Depends(get_current_principal)):
        if not has_any_role(p, *allowed):
            raise HTTPException(status_code=403, detail="insufficient role")
        return p
    return _inner


def get_current_user(
    principal=Depends(require_roles(ROLE_USER)),
    db: Session = Depends(get_db),
) -> User:
    """The CAN user record bound to the authenticated subject (DID or OIDC sub)."""
    u = db.query(User).filter(User.subject == principal["sub"]).first()
    if u is None:
        raise HTTPException(status_code=403, detail="no CAN profile for this identity; create one at POST /identity/users")
    return u


def is_reviewer(principal: dict) -> bool:
    return has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN)


def can_view_user(principal: dict, current: User | None, target_user_id: str) -> bool:
    """Owner, reviewers, admins and auditors may view a user's records."""
    if current is not None and current.id == target_user_id:
        return True
    return has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR)


def current_user_or_none(principal: dict, db: Session) -> User | None:
    return db.query(User).filter(User.subject == principal["sub"]).first()
