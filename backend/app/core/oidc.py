from functools import lru_cache
from typing import Any, Dict
import httpx
from jose import jwt
from jose.exceptions import JWTError

@lru_cache
def _discover(issuer: str) -> Dict[str, Any]:
    r = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
    r.raise_for_status()
    return r.json()

@lru_cache
def _jwks(jwks_uri: str) -> Dict[str, Any]:
    r = httpx.get(jwks_uri, timeout=10)
    r.raise_for_status()
    return r.json()

def verify_access_token(token: str, issuer: str, audience: str) -> Dict[str, Any]:
    conf = _discover(issuer)
    jwks = _jwks(conf["jwks_uri"])

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = next(k for k in jwks["keys"] if k.get("kid") == kid)

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"verify_at_hash": False},
        )
        return claims
    except (StopIteration, JWTError) as e:
        raise ValueError(f"invalid token: {e}") from e

def extract_roles(claims: Dict[str, Any]) -> set[str]:
    roles = set()
    ra = claims.get("realm_access", {})
    roles.update(ra.get("roles", []) or [])
    return roles
