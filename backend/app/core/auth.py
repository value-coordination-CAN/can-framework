from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.oidc import verify_access_token, extract_roles
from app.core.did_session import verify_did_session_token

bearer = HTTPBearer(auto_error=False)

def get_current_principal(creds: HTTPAuthorizationCredentials = Depends(bearer)):
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
            return {
                "sub": claims.get("sub"),
                "email": None,
                "username": None,
                "roles": claims.get("roles", []),
                "assurance": claims.get("assurance"),
                "auth": "did",
                "claims": claims,
            }
        except Exception:
            raise HTTPException(status_code=401, detail="invalid token")

    raise HTTPException(status_code=401, detail="unauthorised")

def require_roles(*required: str):
    def _inner(p=Depends(get_current_principal)):
        roles = set(p["roles"] or [])
        if not set(required).issubset(roles):
            raise HTTPException(status_code=403, detail="insufficient role")
        return p
    return _inner
