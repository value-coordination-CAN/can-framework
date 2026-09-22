import base64
import os
import time

os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AUTH_MODE", "did")
os.environ.setdefault("CAN_JWT_SECRET", "test-secret-" + "x" * 32)
os.environ.setdefault("EXTERNAL_ID_PEPPER", "test-pepper-" + "y" * 32)

import base58  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from nacl.signing import SigningKey  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.did_session import mint_did_session_token  # noqa: E402
from app.db import models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.models import DIDSession  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import network_edge  # noqa: E402,F401


@pytest.fixture()
def db_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(db_session_factory):
    def _get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def new_did() -> tuple[str, SigningKey]:
    sk = SigningKey.generate()
    did = "did:key:z" + base58.b58encode(bytes([0xED, 0x01]) + bytes(sk.verify_key)).decode()
    return did, sk


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def did_login(client) -> tuple[str, str]:
    """Full challenge/verify flow. Returns (did, bearer token) with role can_user."""
    did, sk = new_did()
    ch = client.get("/auth/did/challenge").json()["challenge"]
    sig = sk.sign(ch.encode()).signature
    r = client.post("/auth/did/verify", json={"did": did, "challenge": ch, "signature_b64url": b64url(sig)})
    assert r.status_code == 200, r.text
    return did, r.json()["access_token"]


def token_with_roles(db_session_factory, did: str, roles: list[str]) -> str:
    """A session token with extra roles (as an OIDC provider would grant them)."""
    db = db_session_factory()
    try:
        s = DIDSession(did=did, expires_at=int(time.time()) + 900)
        db.add(s)
        db.commit()
        db.refresh(s)
        return mint_did_session_token(did, s.id, roles=roles)
    finally:
        db.close()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_profile(client, token: str, name: str) -> str:
    r = client.post("/identity/users", json={"display_name": name, "email": f"{name.lower()}@example.org"}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"]
