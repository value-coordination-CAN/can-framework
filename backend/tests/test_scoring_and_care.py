import pytest

from conftest import auth, create_profile, did_login, token_with_roles


@pytest.fixture()
def people(client, db_session_factory):
    did, _ = did_login(client)
    _, alice = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    attester = token_with_roles(db_session_factory, did, ["can_attester"])
    return alice, alice_id, attester


def attest(client, attester, user_id, ledger, metric, value):
    r = client.post(
        "/ledger/entries",
        json={"user_id": user_id, "ledger_type": ledger, "metric": metric, "value": value, "evidence_ref": "ev"},
        headers=auth(attester),
    )
    return r


def test_self_reported_entries_do_not_raise_priority(client, people):
    alice, alice_id, _ = people
    for m in ["peer_validation", "usage_impact", "time_commitment", "outcome_quality"]:
        client.post("/ledger/entries", json={"ledger_type": "contribution", "metric": m, "value": 1.0}, headers=auth(alice))
    s = client.get(f"/score/{alice_id}", headers=auth(alice)).json()
    assert s["overall_score"] == 0.0
    assert s["explanation"]["contribution"]["excluded_self_reported"] == 4


def test_score_uses_yaml_weights_and_explains_itself(client, people):
    alice, alice_id, attester = people
    assert attest(client, attester, alice_id, "contribution", "peer_validation", 1.0).status_code == 200
    assert attest(client, attester, alice_id, "reliability", "completion_rate", 1.0).status_code == 200
    s = client.get(f"/score/{alice_id}", headers=auth(alice)).json()
    # contribution = 0.3 * 1.0 ; reliability = 0.35 * 1.0 ; overall = 0.5*0.3 + 0.5*0.35
    assert s["contribution_score"] == pytest.approx(0.3)
    assert s["reliability_score"] == pytest.approx(0.35)
    assert s["overall_score"] == pytest.approx(0.325)
    exp = s["explanation"]
    assert "formula" in exp and exp["contribution"]["metrics"]["peer_validation"]["entries_counted"] == 1
    # a single extreme entry cannot dominate: missing metrics count as 0, not ignored
    assert exp["contribution"]["metrics"]["usage_impact"]["mean"] == 0.0


def test_care_factors_require_opt_in(client, people):
    alice, alice_id, attester = people
    r = attest(client, attester, alice_id, "care", "health", 1.0)
    assert r.status_code == 403
    assert "consent" in r.json()["detail"]

    r = client.put("/identity/me/care-consent", json={"factors": ["health"]}, headers=auth(alice))
    assert r.status_code == 200 and r.json()["consented_factors"] == ["health"]
    assert attest(client, attester, alice_id, "care", "health", 1.0).status_code == 200

    s = client.get(f"/score/{alice_id}", headers=auth(alice)).json()
    assert s["care_score"] == pytest.approx(0.3)
    assert s["overall_score"] == pytest.approx(0.2 * 0.3)  # care is an uplift only
    assert s["explanation"]["care"]["consented_factors"] == ["health"]


def test_revoking_care_consent_deletes_entries_and_never_lowers_priority(client, people):
    alice, alice_id, attester = people
    attest(client, attester, alice_id, "contribution", "peer_validation", 1.0)
    base = client.get(f"/score/{alice_id}", headers=auth(alice)).json()["overall_score"]

    client.put("/identity/me/care-consent", json={"factors": ["health", "age"]}, headers=auth(alice))
    attest(client, attester, alice_id, "care", "health", 0.8)
    with_care = client.get(f"/score/{alice_id}", headers=auth(alice)).json()["overall_score"]
    assert with_care > base

    r = client.put("/identity/me/care-consent", json={"factors": []}, headers=auth(alice)).json()
    assert r["revoked"] == ["age", "health"] and r["entries_deleted"] == 1
    after = client.get(f"/score/{alice_id}", headers=auth(alice)).json()["overall_score"]
    assert after == pytest.approx(base)
    entries = client.get(f"/ledger/entries/{alice_id}", headers=auth(alice)).json()
    assert not [e for e in entries if e["ledger_type"] == "care"]


def test_unknown_consent_factor_rejected(client, people):
    alice, _, _ = people
    r = client.put("/identity/me/care-consent", json={"factors": ["religion"]}, headers=auth(alice))
    assert r.status_code == 422
