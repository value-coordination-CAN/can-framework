from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings


def mint_did_session_token(
    did: str,
    session_id: str,
    roles: list[str] | None = None,
    assurance_level: str = "A1_DID_ONLY",
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=settings.CAN_DID_SESSION_TTL_SECONDS)
    payload = {
        "sub": did,
        "sid": session_id,
        "typ": "can_did_session",
        "roles": roles or ["can_user"],
        "assurance": assurance_level,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "can-backend",
    }
    return jwt.encode(payload, settings.CAN_JWT_SECRET, algorithm=settings.CAN_JWT_ALG)


def verify_did_session_token(token: str) -> dict:
    """Verify signature, issuer, expiry and type. Revocation is checked against the DB by the caller."""
    try:
        claims = jwt.decode(
            token,
            settings.CAN_JWT_SECRET,
            algorithms=[settings.CAN_JWT_ALG],
            issuer="can-backend",
            options={"require_exp": True, "require_iat": True},
        )
    except Exception as e:
        raise ValueError(f"invalid did session token: {e}") from e
    if claims.get("typ") != "can_did_session":
        raise ValueError("wrong token type")
    if not claims.get("sid"):
        raise ValueError("missing session id")
    return claims
