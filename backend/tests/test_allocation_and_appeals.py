from conftest import auth, create_profile, did_login, token_with_roles


def setup_people(client, db_session_factory):
    _, alice = did_login(client)
    create_profile(client, alice, "Alice")
    r1, _ = did_login(client)
    r2, _ = did_login(client)
    reviewer1 = token_with_roles(db_session_factory, r1, ["can_user", "can_reviewer"])
    reviewer2 = token_with_roles(db_session_factory, r2, ["can_user", "can_reviewer"])
    return alice, reviewer1, reviewer2


def test_request_decision_appeal_resolution_flow(client, db_session_factory):
    alice, reviewer1, reviewer2 = setup_people(client, db_session_factory)

    req = client.post("/allocation/requests", json={"pool": "housing", "description": "family of four"}, headers=auth(alice)).json()
    assert req["status"] == "submitted" and req["score_snapshot_id"]

    detail = client.get(f"/allocation/requests/{req['id']}", headers=auth(alice)).json()
    assert "formula" in detail["score_explanation"]

    queue = client.get("/allocation/requests", params={"status": "submitted"}, headers=auth(reviewer1)).json()
    assert [q["id"] for q in queue] == [req["id"]]

    r = client.post(f"/allocation/requests/{req['id']}/decision", json={"decision": "declined", "reason": "pool full"}, headers=auth(reviewer1))
    assert r.status_code == 200 and r.json()["status"] == "declined"

    appeal = client.post("/appeals/", json={"request_id": req["id"], "reason": "circumstances changed"}, headers=auth(alice)).json()
    assert client.post("/appeals/", json={"request_id": req["id"], "reason": "again"}, headers=auth(alice)).status_code == 409
    assert client.get(f"/appeals/{appeal['id']}", headers=auth(alice)).status_code == 200

    # the original decision-maker cannot resolve the appeal
    r = client.post(f"/appeals/{appeal['id']}/resolve", json={"outcome": "upheld", "note": "n"}, headers=auth(reviewer1))
    assert r.status_code == 403

    r = client.post(f"/appeals/{appeal['id']}/resolve", json={"outcome": "upheld", "note": "new evidence"}, headers=auth(reviewer2))
    assert r.status_code == 200 and r.json()["status"] == "upheld"
    assert client.get(f"/allocation/requests/{req['id']}", headers=auth(alice)).json()["status"] == "reopened"
    assert client.post(f"/appeals/{appeal['id']}/resolve", json={"outcome": "rejected", "note": "n"}, headers=auth(reviewer2)).status_code == 409


def test_users_cannot_decide_requests(client, db_session_factory):
    alice, _, _ = setup_people(client, db_session_factory)
    req = client.post("/allocation/requests", json={"pool": "food", "description": "x"}, headers=auth(alice)).json()
    r = client.post(f"/allocation/requests/{req['id']}/decision", json={"decision": "approved", "reason": "me"}, headers=auth(alice))
    assert r.status_code == 403


def test_reviewer_cannot_decide_own_request(client, db_session_factory):
    did, _ = did_login(client)
    reviewer = token_with_roles(db_session_factory, did, ["can_user", "can_reviewer"])
    create_profile(client, reviewer, "Rita")
    req = client.post("/allocation/requests", json={"pool": "energy", "description": "x"}, headers=auth(reviewer)).json()
    r = client.post(f"/allocation/requests/{req['id']}/decision", json={"decision": "approved", "reason": "x"}, headers=auth(reviewer))
    assert r.status_code == 403
