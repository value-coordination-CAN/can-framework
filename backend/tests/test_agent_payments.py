"""WP-013 demonstration 2: an agent pays within a mandate, and cannot outside it.

Every refusal happens before anything reaches a rail, and every attempt is kept, so the
person can see what their agent tried as well as what it did.
"""
import base64

import pytest
from nacl.signing import SigningKey

from app.bridge.models import Holding, Wallet
from app.core.config import settings
from conftest import auth, b64url, create_profile, did_login, new_did


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture()
def node(monkeypatch):
    key = SigningKey.generate()
    monkeypatch.setattr(settings, "NODE_ID", "node-a")
    monkeypatch.setattr(settings, "NODE_SIGNING_KEY", b64(bytes(key)))
    return key


def fund(db_session_factory, user_id: str, amount: float, currency: str = "USD") -> None:
    db = db_session_factory()
    try:
        wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
        if wallet is None:
            wallet = Wallet(user_id=user_id)
            db.add(wallet)
            db.commit()
            db.refresh(wallet)
        db.add(Holding(wallet_id=wallet.id, layer="fiat", kind="cash", amount=amount, currency=currency,
                       description="opening balance"))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def world(client, node, db_session_factory):
    """A payer with money, a supplier to pay, and an agent the payer has authorised."""
    _, payer = did_login(client)
    payer_id = create_profile(client, payer, "Payer")
    fund(db_session_factory, payer_id, 5000)

    _, supplier = did_login(client)
    supplier_id = create_profile(client, supplier, "Supplier")

    agent_did, agent_key = new_did()
    agent = client.post("/agents/", json={"did": agent_did, "name": "Buying agent", "contact": "ops@example.org",
                                          "scopes": ["general.derive"]}, headers=auth(payer)).json()
    ch = client.get("/auth/did/challenge").json()["challenge"]
    sig = agent_key.sign(ch.encode()).signature
    token = client.post("/agents/auth/verify", json={"did": agent_did, "challenge": ch,
                                                     "signature_b64url": b64url(sig)}).json()["access_token"]
    return {"payer": payer, "payer_id": payer_id, "supplier": supplier, "supplier_id": supplier_id,
            "agent": agent, "agent_did": agent_did, "token": token}


def grant(client, world, **over):
    body = {"agent_id": world["agent"]["id"], "purposes": ["materials"], "currency": "USD",
            "max_per_payment": 500, "max_total": 1200, "payee_user_ids": [world["supplier_id"]],
            "requires_evidence": True, "hours": 24}
    body.update(over)
    r = client.post("/bridge/mandates", json=body, headers=auth(world["payer"]))
    assert r.status_code == 201, r.text
    return r.json()


def attempt(client, world, mandate=None, **over):
    if mandate is None:  # the payer's only mandate
        mandate = client.get("/bridge/mandates", headers=auth(world["payer"])).json()[0]
    body = {"mandate_id": mandate["id"], "payee_user_id": world["supplier_id"], "amount": 400,
            "currency": "USD", "purpose": "materials", "evidence_ref": "invoice 2026-114"}
    body.update(over)
    return client.post("/bridge/payments", json=body, headers=auth(world["token"]))


def cash(client, token) -> float:
    w = client.get("/bridge/wallet", headers=auth(token)).json()
    return w["layers"].get("fiat", {}).get("by_kind", {}).get("cash", 0)


# --- inside the mandate ------------------------------------------------------------------

def test_an_agent_pays_within_its_mandate(client, world):
    mandate = grant(client, world)
    r = attempt(client, world)
    assert r.status_code == 200, r.text
    payment = r.json()
    assert payment["status"] == "settled" and payment["settlement_ref"].startswith("sim:")
    assert cash(client, world["supplier"]) == 400 and cash(client, world["payer"]) == 4600

    # the mandate keeps count
    mine = client.get("/bridge/mandates", headers=auth(world["payer"])).json()[0]
    assert mine["spent_total"] == 400


def test_the_payment_carries_a_trusted_transaction_object(client, world):
    """What travelled with the money: who authorised it, what for, against what."""
    mandate = grant(client, world)
    payment = attempt(client, world).json()
    doc = payment["transaction_object"]
    assert doc["header"]["profile"] == "can.transaction.v1"

    tx = doc["transaction"]
    assert tx["parties"]["payer"] == world["payer_id"] and tx["parties"]["agent"] == world["agent_did"]
    assert tx["parties"]["agent_steward"] == world["payer_id"]
    assert tx["mandate"]["id"] == mandate["id"] and tx["mandate"]["max_per_payment"] == 500
    assert tx["purpose"] == "materials" and tx["evidence_ref"] == "invoice 2026-114"
    assert tx["settlement"]["rail"] == "simulated"
    # and it verifies, like any other document this node issues
    assert client.post("/value/documents/verify", json=doc, headers=auth(world["payer"])).json()["valid"]


def test_a_tampered_transaction_object_does_not_verify(client, world):
    grant(client, world)
    doc = attempt(client, world).json()["transaction_object"]
    doc["transaction"]["amount"] = 40000
    assert client.post("/value/documents/verify", json=doc, headers=auth(world["payer"])).json()["valid"] is False


# --- outside it --------------------------------------------------------------------------

@pytest.mark.parametrize("override,expected", [
    ({"amount": 900}, "above the per-payment limit"),
    ({"purpose": "holidays"}, "not a purpose this mandate allows"),
    ({"evidence_ref": None}, "requires evidence"),
    ({"currency": "EUR"}, "the mandate is in USD"),
])
def test_payments_outside_the_mandate_are_refused(client, world, override, expected):
    mandate = grant(client, world)
    r = attempt(client, world, **override)
    assert r.status_code == 402
    assert expected in r.json()["detail"]["refused"]
    # nothing moved, and the mandate is untouched
    assert cash(client, world["supplier"]) == 0 and cash(client, world["payer"]) == 5000
    assert client.get("/bridge/mandates", headers=auth(world["payer"])).json()[0]["spent_total"] == 0


def test_a_payee_not_on_the_mandate_is_refused(client, world):
    mandate = grant(client, world)
    _, other = did_login(client)
    other_id = create_profile(client, other, "SomeoneElse")
    r = attempt(client, world, payee_user_id=other_id)
    assert r.status_code == 402 and "not on the mandate" in r.json()["detail"]["refused"]


def test_the_total_is_a_ceiling_not_a_suggestion(client, world):
    mandate = grant(client, world)
    assert attempt(client, world, amount=500).status_code == 200
    assert attempt(client, world, amount=500).status_code == 200   # 1000 of 1200 spent
    over = attempt(client, world, amount=500)
    assert over.status_code == 402 and "200.0 remains" in over.json()["detail"]["refused"]
    assert attempt(client, world, amount=200).status_code == 200   # exactly the remainder
    exhausted = attempt(client, world, amount=1)
    assert exhausted.status_code == 402 and "exhausted" in exhausted.json()["detail"]["refused"]


def test_revoking_stops_the_next_payment(client, world):
    mandate = grant(client, world)
    assert attempt(client, world).status_code == 200
    client.post(f"/bridge/mandates/{mandate['id']}/revoke", params={"reason": "no longer needed"},
                headers=auth(world["payer"]))
    r = attempt(client, world)
    assert r.status_code == 402 and "revoked" in r.json()["detail"]["refused"]


def test_an_expired_mandate_is_refused(client, world, db_session_factory):
    from datetime import timedelta

    from app.bridge.mandate_models import PaymentMandate
    from app.core.time import utcnow

    mandate = grant(client, world)
    db = db_session_factory()
    try:
        db.get(PaymentMandate, mandate["id"]).expires_at = utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    r = attempt(client, world)
    assert r.status_code == 402 and "expired" in r.json()["detail"]["refused"]


def test_an_agent_cannot_use_a_mandate_granted_to_another(client, world):
    mandate = grant(client, world)
    other_did, other_key = new_did()
    client.post("/agents/", json={"did": other_did, "name": "Other agent", "contact": "x@example.org",
                                  "scopes": []}, headers=auth(world["payer"]))
    ch = client.get("/auth/did/challenge").json()["challenge"]
    token = client.post("/agents/auth/verify", json={"did": other_did, "challenge": ch,
                        "signature_b64url": b64url(other_key.sign(ch.encode()).signature)}).json()["access_token"]
    r = client.post("/bridge/payments", json={"mandate_id": mandate["id"], "payee_user_id": world["supplier_id"],
                                              "amount": 100, "currency": "USD", "purpose": "materials",
                                              "evidence_ref": "invoice"}, headers=auth(token))
    assert r.status_code == 402 and "different agent" in r.json()["detail"]["refused"]


def test_a_person_cannot_pay_through_the_agent_endpoint(client, world):
    mandate = grant(client, world)
    r = client.post("/bridge/payments", json={"mandate_id": mandate["id"], "payee_user_id": world["supplier_id"],
                                              "amount": 100, "currency": "USD", "purpose": "materials",
                                              "evidence_ref": "invoice"}, headers=auth(world["payer"]))
    assert r.status_code == 403


def test_money_it_does_not_have_is_refused(client, world):
    mandate = grant(client, world, max_per_payment=9000, max_total=9000)
    r = attempt(client, world, amount=6000)
    assert r.status_code == 402 and "less than" in r.json()["detail"]["refused"]


def test_pledged_money_is_not_spendable_by_an_agent(client, world, db_session_factory):
    """Value pledged as security cannot be paid away by an agent either."""
    mandate = grant(client, world, max_per_payment=5000, max_total=5000)
    wallet = client.get("/bridge/wallet", headers=auth(world["payer"])).json()
    holding = [h for h in wallet["holdings"] if h["kind"] == "cash"][0]
    db = db_session_factory()
    try:
        from app.bridge.models import Pledge
        db.add(Pledge(holding_id=holding["id"], amount=4800, note="security"))
        db.commit()
    finally:
        db.close()
    r = attempt(client, world, amount=400)
    assert r.status_code == 402 and "free of pledges" in r.json()["detail"]["refused"]


# --- the audit trail ----------------------------------------------------------------------

def test_the_payer_sees_what_the_agent_tried_as_well_as_what_it_did(client, world):
    grant(client, world)
    attempt(client, world)                      # settled
    attempt(client, world, amount=900)          # refused
    attempt(client, world, purpose="holidays")  # refused

    all_attempts = client.get("/bridge/payments", headers=auth(world["payer"])).json()
    assert len(all_attempts) == 3
    refused = client.get("/bridge/payments", params={"status": "refused"}, headers=auth(world["payer"])).json()
    assert len(refused) == 2 and all(p["refusal_reason"] for p in refused)
    assert all(p["settlement_ref"] is None for p in refused)   # nothing reached a rail

    # the supplier sees the payment to them, and nothing else
    theirs = client.get("/bridge/payments", headers=auth(world["supplier"])).json()
    assert [p["status"] for p in theirs] == ["settled"]


def test_an_unrelated_person_sees_none_of_it(client, world):
    grant(client, world)
    attempt(client, world)
    _, stranger = did_login(client)
    create_profile(client, stranger, "Stranger")
    assert client.get("/bridge/payments", headers=auth(stranger)).json() == []
