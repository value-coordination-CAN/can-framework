import pytest

from app.core.config import Settings, validate_settings
from conftest import auth, b64url, did_login, new_did


def test_did_login_and_logout_revokes_session(client):
    _, token = did_login(client)
    assert client.get("/identity/users/me", headers=auth(token)).status_code == 403  # no profile yet, but token valid
    assert client.post("/auth/did/logout", headers=auth(token)).status_code == 200
    assert client.get("/identity/users/me", headers=auth(token)).status_code == 401


def test_challenge_is_single_use_even_after_failed_proof(client):
    did, sk = new_did()
    other_did, other_sk = new_did()
    ch = client.get("/auth/did/challenge").json()["challenge"]
    bad = other_sk.sign(ch.encode()).signature
    r = client.post("/auth/did/verify", json={"did": did, "challenge": ch, "signature_b64url": b64url(bad)})
    assert r.status_code == 401
    good = sk.sign(ch.encode()).signature
    r = client.post("/auth/did/verify", json={"did": did, "challenge": ch, "signature_b64url": b64url(good)})
    assert r.status_code == 400  # already consumed


@pytest.mark.parametrize(
    "did,sig",
    [
        ("did:web:example.org", "AAAA"),
        ("did:key:z0OIl", "AAAA"),  # not base58
        (None, "not*base64"),
        (None, "AAAA"),  # wrong signature length
    ],
)
def test_malformed_did_or_signature_is_400_not_500(client, did, sig):
    if did is None:
        did, _ = new_did()
    ch = client.get("/auth/did/challenge").json()["challenge"]
    r = client.post("/auth/did/verify", json={"did": did, "challenge": ch, "signature_b64url": sig})
    assert r.status_code == 400, r.text


def test_forged_token_rejected(client):
    from jose import jwt

    forged = jwt.encode(
        {"sub": "did:key:zX", "sid": "x", "typ": "can_did_session", "roles": ["can_admin"], "iat": 0, "exp": 9999999999, "iss": "can-backend"},
        "change-me",
        algorithm="HS256",
    )
    assert client.get("/identity/users/me", headers=auth(forged)).status_code == 401


def test_insecure_settings_refused_outside_dev():
    with pytest.raises(RuntimeError):
        validate_settings(Settings(ENV="prod", CAN_JWT_SECRET="change-me", EXTERNAL_ID_PEPPER="change-me"))
    validate_settings(Settings(ENV="prod", CAN_JWT_SECRET="s" * 40, EXTERNAL_ID_PEPPER="p" * 40))
    validate_settings(Settings(ENV="dev", CAN_JWT_SECRET="change-me"))
