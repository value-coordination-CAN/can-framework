import threading
import time
from typing import Any, Dict

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import settings

_lock = threading.Lock()
_discovery: Dict[str, Dict[str, Any]] = {}
_jwks: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _discover(issuer: str) -> Dict[str, Any]:
    with _lock:
        if issuer in _discovery:
            return _discovery[issuer]
    r = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
    r.raise_for_status()
    conf = r.json()
    with _lock:
        _discovery[issuer] = conf
    return conf


def _get_jwks(jwks_uri: str, force: bool = False) -> Dict[str, Any]:
    now = time.monotonic()
    with _lock:
        cached = _jwks.get(jwks_uri)
        if cached and not force and now - cached[0] < settings.OIDC_JWKS_TTL_SECONDS:
            return cached[1]
    r = httpx.get(jwks_uri, timeout=10)
    r.raise_for_status()
    keys = r.json()
    with _lock:
        _jwks[jwks_uri] = (now, keys)
    return keys


def _find_key(jwks: Dict[str, Any], kid: str | None) -> Dict[str, Any] | None:
    return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)


def verify_access_token(token: str, issuer: str, audience: str) -> Dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise ValueError(f"invalid token: {e}") from e
    kid = header.get("kid")

    conf = _discover(issuer)
    key = _find_key(_get_jwks(conf["jwks_uri"]), kid)
    if key is None:
        # Unknown kid: the issuer may have rotated its keys, so refresh once.
        key = _find_key(_get_jwks(conf["jwks_uri"], force=True), kid)
    if key is None:
        raise ValueError("invalid token: unknown signing key")

    try:
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise ValueError(f"invalid token: {e}") from e


def extract_roles(claims: Dict[str, Any]) -> set[str]:
    roles = set()
    ra = claims.get("realm_access", {})
    roles.update(ra.get("roles", []) or [])
    return roles
