from conftest import auth, create_profile, did_login, token_with_roles


def test_one_profile_per_identity_and_email_hidden_from_others(client):
    _, alice = did_login(client)
    _, bob = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    create_profile(client, bob, "Bob")

    r = client.post("/identity/users", json={"display_name": "Alice2", "email": "a2@example.org"}, headers=auth(alice))
    assert r.status_code == 409

    seen_by_bob = client.get(f"/identity/users/{alice_id}", headers=auth(bob)).json()
    assert "email" not in seen_by_bob
    seen_by_alice = client.get(f"/identity/users/{alice_id}", headers=auth(alice)).json()
    assert seen_by_alice["email"] == "alice@example.org"


def test_cannot_write_ledger_entries_for_someone_else(client):
    _, alice = did_login(client)
    _, bob = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    create_profile(client, bob, "Bob")

    r = client.post(
        "/ledger/entries",
        json={"user_id": alice_id, "ledger_type": "contribution", "metric": "peer_validation", "value": 1.0, "evidence_ref": "x"},
        headers=auth(bob),
    )
    assert r.status_code == 403


def test_values_are_capped_and_metrics_validated(client):
    _, alice = did_login(client)
    create_profile(client, alice, "Alice")
    r = client.post("/ledger/entries", json={"ledger_type": "contribution", "metric": "peer_validation", "value": 1000000}, headers=auth(alice))
    assert r.status_code == 422
    r = client.post("/ledger/entries", json={"ledger_type": "contribution", "metric": "made_up", "value": 0.5}, headers=auth(alice))
    assert r.status_code == 422


def test_attester_needs_evidence_and_cannot_be_used_without_role(client, db_session_factory):
    did, _ = did_login(client)
    _, alice = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    attester = token_with_roles(db_session_factory, did, ["can_attester"])

    body = {"user_id": alice_id, "ledger_type": "reliability", "metric": "attendance", "value": 0.9}
    assert client.post("/ledger/entries", json=body, headers=auth(attester)).status_code == 422
    r = client.post("/ledger/entries", json={**body, "evidence_ref": "rota:2026-09"}, headers=auth(attester))
    assert r.status_code == 200, r.text
    assert r.json()["self_reported"] is False


def test_scores_and_requests_are_private(client):
    _, alice = did_login(client)
    _, bob = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    create_profile(client, bob, "Bob")

    assert client.get(f"/score/{alice_id}", headers=auth(bob)).status_code == 403
    assert client.get(f"/ledger/entries/{alice_id}", headers=auth(bob)).status_code == 403

    req = client.post("/allocation/requests", json={"pool": "housing", "description": "need"}, headers=auth(alice)).json()
    assert client.get(f"/allocation/requests/{req['id']}", headers=auth(bob)).status_code == 403
    assert client.post("/appeals/", json={"request_id": req["id"], "reason": "x"}, headers=auth(bob)).status_code == 403
    assert client.get("/allocation/requests", headers=auth(bob)).status_code == 403


def test_network_path_only_from_self(client):
    _, alice = did_login(client)
    _, bob = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    create_profile(client, bob, "Bob")
    r = client.get("/network/path", params={"to": "li:abc", "from": alice_id}, headers=auth(bob))
    assert r.status_code == 403
