import pytest

from app.agents.service import canonical_hash
from conftest import auth, b64url, create_profile, did_login, new_did, token_with_roles

DERIVATION = {
    "kind": "valuation",
    "subject_ref": "asset:demo",
    "statement": "Value is 15,120,000 on the recorded evidence.",
    "inputs": {"units": 100, "occupancy": 0.9, "rent_per_unit_month": 1000, "opex_ratio": 0.3, "cap_rate": 0.05},
    "output": {"value": 15120000.0},
    "method": "can-value-engine 0.1 (income model)",
    "confidence": 0.8,
}


def register_agent(client, steward_token, did, scopes=("value.derive",), **extra):
    return client.post("/agents/", json={"did": did, "name": "Test agent", "model": "test-model-1",
                                         "contact": "steward@example.org", "scopes": list(scopes), **extra},
                       headers=auth(steward_token))


def test_register_is_public_and_shows_who_answers(client, agent):
    """Anyone affected can find the steward without an account."""
    client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"]))
    entries = client.get("/agents/register").json()  # no Authorization header
    entry = next(e for e in entries if e["id"] == agent["agent"]["id"])
    assert entry["contact"] == "steward@example.org"
    assert entry["status"] == "active" and entry["did"] == agent["did"]
    assert entry["records"] == {"total": 1, "unreviewed": 1, "confirmed": 0, "rejected": 0,
                                "superseded": 0, "recomputed": 0, "failed_recomputation": 0}
    # the steward's own name is published only if they chose to
    assert entry["steward_name"] is None
    one = client.get(f"/agents/register/{agent['agent']['id']}").json()
    assert one["id"] == entry["id"]


def test_register_does_not_publish_what_the_agent_wrote(client, agent):
    client.post("/agents/records", json={**DERIVATION, "subject_ref": "user:private-person-id"},
                headers=auth(agent["token"]))
    body = client.get("/agents/register").text
    assert "private-person-id" not in body
    assert DERIVATION["statement"] not in body
    assert "occupancy" not in body
    # reading a record itself still needs an account
    assert client.get("/agents/records").status_code in {401, 403}


def test_register_shows_participation(client, agent):
    """An agent's contribution is visible: what it did, how much, and how it held up."""
    for kind, scope_ok in [("valuation", True), ("valuation", True), ("check", True)]:
        client.post("/agents/records", json={**DERIVATION, "kind": kind}, headers=auth(agent["token"]))
    rec = client.get("/agents/records", headers=auth(agent["steward"])).json()[0]
    client.post(f"/agents/records/{rec['id']}/review", json={"accept": True, "note": "checked"}, headers=auth(agent["steward"]))
    client.post(f"/agents/records/{rec['id']}/recompute", json={"output": DERIVATION["output"], "method": "rerun"},
                headers=auth(agent["steward"]))

    p = client.get(f"/agents/register/{agent['agent']['id']}").json()["participation"]
    assert p["contributions_by_kind"] == {"valuation": 2, "check": 1}
    assert p["subjects_contributed_to"] == 1
    assert p["first_contribution"] and p["latest_contribution"]
    assert p["confirmed_share"] == 1.0 and p["recomputation_pass_rate"] == 1.0
    # what the agent contributes belongs to the steward; the agent holds nothing
    assert p["value_accrues_to"] == "steward" and p["holds_entitlements"] is False


def test_register_shows_how_an_agents_work_held_up(client, agent):
    rec = client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"])).json()
    client.post(f"/agents/records/{rec['id']}/recompute", json={"output": {"value": 1.0}, "method": "rerun"},
                headers=auth(agent["steward"]))
    entry = client.get(f"/agents/register/{agent['agent']['id']}").json()
    assert entry["records"]["failed_recomputation"] == 1 and entry["records"]["superseded"] == 1


def test_steward_can_publish_their_name_and_change_the_contact(client, agent):
    aid = agent["agent"]["id"]
    client.patch(f"/agents/{aid}", json={"steward_name_public": True, "contact": "oversight@example.org"},
                 headers=auth(agent["steward"]))
    entry = client.get(f"/agents/register/{aid}").json()
    assert entry["steward_name"] == "Steward" and entry["contact"] == "oversight@example.org"


def test_revoked_agents_stay_listed(client, agent):
    aid = agent["agent"]["id"]
    client.patch(f"/agents/{aid}", json={"status": "revoked", "reason": "replaced"}, headers=auth(agent["steward"]))
    entry = client.get(f"/agents/register/{aid}").json()
    assert entry["status"] == "revoked" and entry["revoked_reason"] == "replaced"
    assert [e["id"] for e in client.get("/agents/register", params={"status": "revoked"}).json()] == [aid]


def test_register_can_be_searched(client, agent):
    assert client.get("/agents/register", params={"q": "test-model-1"}).json()[0]["id"] == agent["agent"]["id"]
    assert client.get("/agents/register", params={"q": "no-such-agent"}).json() == []


def test_a_contact_is_required_to_register(client):
    _, steward = did_login(client)
    create_profile(client, steward, "NoContact")
    did, _ = new_did()
    r = client.post("/agents/", json={"did": did, "name": "Anonymous agent", "scopes": []}, headers=auth(steward))
    assert r.status_code == 422


def agent_sign_in(client, did, sk):
    ch = client.get("/auth/did/challenge").json()["challenge"]
    sig = sk.sign(ch.encode()).signature
    return client.post("/agents/auth/verify", json={"did": did, "challenge": ch, "signature_b64url": b64url(sig)})


@pytest.fixture()
def agent(client):
    _, steward = did_login(client)
    steward_id = create_profile(client, steward, "Steward")
    did, sk = new_did()
    a = register_agent(client, steward, did).json()
    token = agent_sign_in(client, did, sk).json()["access_token"]
    return {"steward": steward, "steward_id": steward_id, "did": did, "sk": sk, "agent": a, "token": token}


def test_rules_are_public_and_state_the_terms(client):
    r = client.get("/agents/rules").json()
    assert r["holdings"]["may_hold_entitlement"] is False
    assert r["holdings"]["value_accrues_to"] == "steward"
    assert r["recomputation"]["on_mismatch"] == "supersede"
    assert any("derive" in p for p in r["principles"])


def test_no_steward_no_write_access(client):
    did, sk = new_did()
    r = agent_sign_in(client, did, sk)
    assert r.status_code == 403 and "register" in r.json()["detail"]


def test_agent_records_a_derivation_with_hashes(client, agent):
    r = client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"]))
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["status"] == "unreviewed" and rec["recompute_status"] == "unchecked"
    assert rec["inputs_hash"] == canonical_hash(DERIVATION["inputs"])
    assert rec["output_hash"] == canonical_hash(DERIVATION["output"])
    # anyone signed in can read it and challenge it
    assert client.get(f"/agents/records/{rec['id']}", headers=auth(agent["steward"])).status_code == 200


def test_scope_is_enforced(client):
    _, steward = did_login(client)
    create_profile(client, steward, "Steward2")
    did, sk = new_did()
    register_agent(client, steward, did, scopes=("general.derive",))
    token = agent_sign_in(client, did, sk).json()["access_token"]
    r = client.post("/agents/records", json=DERIVATION, headers=auth(token))
    assert r.status_code == 403 and "scopes" in r.json()["detail"]
    ok = client.post("/agents/records", json={**DERIVATION, "kind": "summary"}, headers=auth(token))
    assert ok.status_code == 201


def test_recomputation_mismatch_supersedes_automatically(client, agent):
    rec = client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"])).json()
    # the agent that produced it cannot mark its own work as reproduced
    same = client.post(f"/agents/records/{rec['id']}/recompute",
                       json={"output": DERIVATION["output"], "method": "rerun"}, headers=auth(agent["token"]))
    assert same.status_code == 403

    match = client.post(f"/agents/records/{rec['id']}/recompute",
                        json={"output": {"value": 15120000.0}, "method": "independent rerun"},
                        headers=auth(agent["steward"])).json()
    assert match["matched"] and match["record"]["recompute_status"] == "matched"

    rec2 = client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"])).json()
    bad = client.post(f"/agents/records/{rec2['id']}/recompute",
                      json={"output": {"value": 9999999.0}, "method": "independent rerun"},
                      headers=auth(agent["steward"])).json()
    assert bad["matched"] is False and bad["superseded"] is True
    assert bad["record"]["status"] == "superseded"
    assert client.get(f"/agents/records/{rec2['id']}/recomputations", headers=auth(agent["steward"])).json()[0]["result"] == "mismatched"


def test_writes_pause_when_the_queue_is_full(client):
    _, steward = did_login(client)
    create_profile(client, steward, "Steward3")
    did, sk = new_did()
    register_agent(client, steward, did, max_unreviewed=2)
    token = agent_sign_in(client, did, sk).json()["access_token"]

    ids = []
    for i in range(2):
        r = client.post("/agents/records", json={**DERIVATION, "statement": f"derivation {i}"}, headers=auth(token))
        assert r.status_code == 201
        ids.append(r.json()["id"])

    blocked = client.post("/agents/records", json=DERIVATION, headers=auth(token))
    assert blocked.status_code == 429 and "queue is full" in blocked.json()["detail"]
    assert client.get("/agents/me/queue", headers=auth(token)).json()["writes_paused"] is True

    # a human working through the queue is what frees it
    client.post(f"/agents/records/{ids[0]}/review", json={"accept": True, "note": "checked the inputs"}, headers=auth(steward))
    q = client.get("/agents/me/queue", headers=auth(token)).json()
    assert q["writes_paused"] is False and q["remaining"] == 1
    assert client.post("/agents/records", json=DERIVATION, headers=auth(token)).status_code == 201


def test_steward_ceiling_is_shared_across_their_agents(client, monkeypatch):
    """Registering more agents does not create review capacity."""
    from app.agents import config as agent_config

    rules = agent_config.load_agent_rules()
    monkeypatch.setattr(rules, "max_unreviewed_per_steward", 3, raising=False)

    _, steward = did_login(client)
    create_profile(client, steward, "BusySteward")
    tokens = []
    for i in range(2):
        did, sk = new_did()
        assert register_agent(client, steward, did, max_unreviewed=10).status_code == 200
        tokens.append(agent_sign_in(client, did, sk).json()["access_token"])

    ids = []
    for i in range(3):  # three records, spread across two agents
        r = client.post("/agents/records", json={**DERIVATION, "statement": f"d{i}"}, headers=auth(tokens[i % 2]))
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    # the second agent is well inside its own ceiling, but the steward's queue is full
    blocked = client.post("/agents/records", json=DERIVATION, headers=auth(tokens[1]))
    assert blocked.status_code == 429 and "steward" in blocked.json()["detail"]
    q = client.get("/agents/me/queue", headers=auth(tokens[1])).json()
    assert q["writes_paused"] is False and q["steward"]["writes_paused"] is True

    sq = client.get("/agents/steward/queue", headers=auth(steward)).json()
    assert sq["unreviewed"] == 3 and sq["agents"] == 2

    client.post(f"/agents/records/{ids[0]}/review", json={"accept": True, "note": "checked"}, headers=auth(steward))
    assert client.post("/agents/records", json=DERIVATION, headers=auth(tokens[1])).status_code == 201


def test_a_steward_cannot_register_unlimited_agents(client, monkeypatch):
    from app.agents import config as agent_config

    rules = agent_config.load_agent_rules()
    monkeypatch.setattr(rules, "max_agents_per_steward", 2, raising=False)

    _, steward = did_login(client)
    create_profile(client, steward, "Collector")
    dids = [new_did() for _ in range(3)]
    assert register_agent(client, steward, dids[0][0]).status_code == 200
    second = register_agent(client, steward, dids[1][0])
    assert second.status_code == 200
    third = register_agent(client, steward, dids[2][0])
    assert third.status_code == 403 and "limit per steward" in third.json()["detail"]

    # revoking one frees a place
    client.patch(f"/agents/{second.json()['id']}", json={"status": "revoked", "reason": "retired"}, headers=auth(steward))
    assert register_agent(client, steward, dids[2][0]).status_code == 200


def test_steward_can_revoke_immediately(client, agent):
    r = client.patch(f"/agents/{agent['agent']['id']}", json={"status": "revoked", "reason": "no longer needed"},
                     headers=auth(agent["steward"]))
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    # the live token stops working at once
    assert client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"])).status_code == 401
    assert agent_sign_in(client, agent["did"], agent["sk"]).status_code == 403


def test_only_the_steward_or_an_admin_changes_an_agent(client, agent):
    _, other = did_login(client)
    create_profile(client, other, "Other")
    r = client.patch(f"/agents/{agent['agent']['id']}", json={"status": "suspended"}, headers=auth(other))
    assert r.status_code == 403


def test_agents_cannot_hold_or_become_people(client, agent):
    """An agent token can record derivations and nothing else."""
    t = auth(agent["token"])
    assert client.post("/identity/users", json={"display_name": "Agent", "email": "agent@example.org"}, headers=t).status_code == 403
    assert client.get("/bridge/wallet", headers=t).status_code == 403
    assert client.post("/value/assets", json={"name": "x", "kind": "y"}, headers=t).status_code == 403
    assert client.post("/allocation/requests", json={"pool": "housing", "description": "x"}, headers=t).status_code == 403
    assert client.post("/ledger/entries", json={"ledger_type": "contribution", "metric": "peer_validation", "value": 1}, headers=t).status_code == 403
    assert client.post("/agents/", json={"did": "did:key:zOther", "name": "n", "contact": "a@example.org", "scopes": []},
                       headers=t).status_code == 403


def test_a_persons_did_cannot_be_registered_as_an_agent(client, agent):
    person_did, person_token = did_login(client)
    create_profile(client, person_token, "Person")
    r = client.post("/agents/", json={"did": person_did, "name": "n", "contact": "s@example.org", "scopes": []},
                    headers=auth(agent["steward"]))
    assert r.status_code == 409 and "person" in r.json()["detail"]
    # and the same DID cannot be registered twice
    dup = client.post("/agents/", json={"did": agent["did"], "name": "n", "contact": "s@example.org", "scopes": []},
                      headers=auth(agent["steward"]))
    assert dup.status_code == 409


def test_reviewer_can_review_and_records_are_attributable(client, agent, db_session_factory):
    rec = client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"])).json()
    rev_did, _ = did_login(client)
    reviewer = token_with_roles(db_session_factory, rev_did, ["can_user", "can_reviewer"])
    create_profile(client, reviewer, "Reviewer")
    r = client.post(f"/agents/records/{rec['id']}/review", json={"accept": False, "note": "inputs do not support this"},
                    headers=auth(reviewer))
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    again = client.post(f"/agents/records/{rec['id']}/review", json={"accept": True, "note": "x"}, headers=auth(reviewer))
    assert again.status_code == 409
    listed = client.get("/agents/records", params={"agent_id": agent["agent"]["id"]}, headers=auth(agent["steward"])).json()
    assert listed[0]["agent_id"] == agent["agent"]["id"]


def test_agents_are_exported_and_removed_with_the_steward(client, agent):
    client.post("/agents/records", json=DERIVATION, headers=auth(agent["token"]))
    data = client.get("/identity/users/me/export", headers=auth(agent["steward"])).json()
    assert data["agents_stewarded"][0]["did"] == agent["did"]
    counts = client.delete("/identity/users/me", params={"confirm": "true"}, headers=auth(agent["steward"])).json()["counts"]
    assert counts["agents_stewarded"] == 1 and counts["agent_derived_records"] == 1
    # with the steward gone, the agent cannot sign in again
    assert agent_sign_in(client, agent["did"], agent["sk"]).status_code == 403
