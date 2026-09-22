import pytest

from app.db.models import DeletionRecord, DIDSession, LedgerEntry, User
from app.services.account import pseudonym
from conftest import auth, create_profile, did_login, token_with_roles


@pytest.fixture()
def world(client, db_session_factory):
    alice_did, alice = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    att_did, _ = did_login(client)
    attester = token_with_roles(db_session_factory, att_did, ["can_attester"])
    rev_did, _ = did_login(client)
    reviewer = token_with_roles(db_session_factory, rev_did, ["can_user", "can_reviewer"])
    return {
        "alice": alice, "alice_id": alice_id, "alice_did": alice_did,
        "attester": attester, "att_did": att_did,
        "reviewer": reviewer, "rev_did": rev_did,
    }


def attest(client, token, user_id, value, metric="attendance"):
    r = client.post(
        "/ledger/entries",
        json={"user_id": user_id, "ledger_type": "reliability", "metric": metric, "value": value, "evidence_ref": "rota"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def score(client, w):
    return client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()


# ---------- right to correction ----------

def test_dispute_corrected_supersedes_and_rescores(client, world):
    w = world
    entry = attest(client, w["attester"], w["alice_id"], 0.2)
    before = score(client, w)["reliability_score"]

    d = client.post(f"/ledger/entries/{entry}/disputes", json={"reason": "I attended", "proposed_value": 0.9}, headers=auth(w["alice"]))
    assert d.status_code == 200, d.text
    d = d.json()
    # still counts while under dispute, and the explanation says so
    s = score(client, w)
    assert s["reliability_score"] == before and s["explanation"]["entries_under_dispute"] == 1

    assert client.get("/ledger/disputes", headers=auth(w["reviewer"])).json()[0]["id"] == d["id"]
    r = client.post(
        f"/ledger/disputes/{d['id']}/resolve",
        json={"outcome": "corrected", "note": "register checked", "corrected_value": 0.9},
        headers=auth(w["reviewer"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "corrected" and r.json()["corrected_entry_id"]

    entries = client.get(f"/ledger/entries/{w['alice_id']}", headers=auth(w["alice"])).json()
    old = next(e for e in entries if e["id"] == entry)
    new = next(e for e in entries if e["id"] == r.json()["corrected_entry_id"])
    assert old["status"] == "superseded" and new["supersedes_id"] == entry and new["value"] == 0.9
    assert score(client, w)["reliability_score"] == pytest.approx(0.25 * 0.9)


def test_dispute_removed_and_rejected(client, world):
    w = world
    e1 = attest(client, w["attester"], w["alice_id"], 0.1)
    e2 = attest(client, w["attester"], w["alice_id"], 0.5, metric="responsiveness")
    d1 = client.post(f"/ledger/entries/{e1}/disputes", json={"reason": "not me"}, headers=auth(w["alice"])).json()
    d2 = client.post(f"/ledger/entries/{e2}/disputes", json={"reason": "too low"}, headers=auth(w["alice"])).json()

    client.post(f"/ledger/disputes/{d1['id']}/resolve", json={"outcome": "removed", "note": "wrong person"}, headers=auth(w["reviewer"]))
    client.post(f"/ledger/disputes/{d2['id']}/resolve", json={"outcome": "rejected", "note": "evidence holds"}, headers=auth(w["reviewer"]))

    s = score(client, w)["explanation"]["reliability"]["metrics"]
    assert s["attendance"]["entries_counted"] == 0
    assert s["responsiveness"]["mean"] == 0.5


def test_dispute_rules(client, world):
    w = world
    entry = attest(client, w["attester"], w["alice_id"], 0.3)
    _, bob = did_login(client)
    create_profile(client, bob, "Bob")

    # only the person the entry is about can dispute it
    assert client.post(f"/ledger/entries/{entry}/disputes", json={"reason": "x"}, headers=auth(bob)).status_code == 403
    d = client.post(f"/ledger/entries/{entry}/disputes", json={"reason": "x"}, headers=auth(w["alice"])).json()
    # one open dispute per entry
    assert client.post(f"/ledger/entries/{entry}/disputes", json={"reason": "y"}, headers=auth(w["alice"])).status_code == 409
    # the person cannot resolve their own dispute, nor can ordinary users
    assert client.post(f"/ledger/disputes/{d['id']}/resolve", json={"outcome": "removed", "note": "n"}, headers=auth(w["alice"])).status_code == 403
    # 'corrected' needs a value
    r = client.post(f"/ledger/disputes/{d['id']}/resolve", json={"outcome": "corrected", "note": "n"}, headers=auth(w["reviewer"]))
    assert r.status_code == 409
    # others cannot read the dispute
    assert client.get(f"/ledger/disputes/{d['id']}", headers=auth(bob)).status_code == 403
    assert client.get(f"/ledger/disputes/{d['id']}", headers=auth(w["alice"])).status_code == 200


def test_original_attester_cannot_resolve(client, world, db_session_factory):
    w = world
    both = token_with_roles(db_session_factory, w["att_did"], ["can_attester", "can_reviewer"])
    entry = attest(client, both, w["alice_id"], 0.3)
    d = client.post(f"/ledger/entries/{entry}/disputes", json={"reason": "x"}, headers=auth(w["alice"])).json()
    r = client.post(f"/ledger/disputes/{d['id']}/resolve", json={"outcome": "rejected", "note": "n"}, headers=auth(both))
    assert r.status_code == 403


def test_self_reported_entries_are_deleted_not_disputed(client, world):
    w = world
    own = client.post("/ledger/entries", json={"ledger_type": "contribution", "metric": "time_commitment", "value": 0.4}, headers=auth(w["alice"])).json()
    assert client.post(f"/ledger/entries/{own['id']}/disputes", json={"reason": "x"}, headers=auth(w["alice"])).status_code == 409
    assert client.delete(f"/ledger/entries/{own['id']}", headers=auth(w["alice"])).status_code == 200
    attested = attest(client, w["attester"], w["alice_id"], 0.3)
    assert client.delete(f"/ledger/entries/{attested}", headers=auth(w["alice"])).status_code == 409


# ---------- right of access and withdrawal ----------

def test_export_contains_everything(client, world):
    w = world
    attest(client, w["attester"], w["alice_id"], 0.3)
    client.put("/identity/me/care-consent", json={"factors": ["health"]}, headers=auth(w["alice"]))
    client.post("/allocation/requests", json={"pool": "housing", "description": "x"}, headers=auth(w["alice"]))
    data = client.get("/identity/users/me/export", headers=auth(w["alice"])).json()
    assert data["profile"]["id"] == w["alice_id"]
    assert len(data["ledger_entries"]) == 1 and len(data["care_consents"]) == 1
    assert len(data["allocation_requests"]) == 1 and len(data["score_snapshots"]) == 1


def test_account_deletion_erases_and_pseudonymises(client, world, db_session_factory):
    w = world
    # Alice is also an attester for Bob, so her identity appears on Bob's record
    alice_attester = token_with_roles(db_session_factory, w["alice_did"], ["can_user", "can_attester"])
    _, bob = did_login(client)
    bob_id = create_profile(client, bob, "Bob")
    bob_entry = attest(client, alice_attester, bob_id, 0.7)

    e = attest(client, w["attester"], w["alice_id"], 0.3)
    client.post(f"/ledger/entries/{e}/disputes", json={"reason": "x"}, headers=auth(w["alice"]))
    client.put("/identity/me/care-consent", json={"factors": ["health"]}, headers=auth(w["alice"]))
    req = client.post("/allocation/requests", json={"pool": "food", "description": "x"}, headers=auth(w["alice"])).json()
    client.post("/appeals/", json={"request_id": req["id"], "reason": "x"}, headers=auth(w["alice"]))
    client.post("/integrations/linkedin/import", files={"file": ("c.csv", "URL\nhttps://x/in/a\n", "text/csv")}, headers=auth(w["alice"]))

    assert client.delete("/identity/users/me", headers=auth(w["alice"])).status_code == 400  # needs confirm
    r = client.delete("/identity/users/me", params={"confirm": "true"}, headers=auth(w["alice"]))
    assert r.status_code == 200, r.text
    counts = r.json()["counts"]
    assert counts["ledger_entries"] == 1 and counts["appeals"] == 1 and counts["network_edges"] == 1
    assert counts["pseudonymised_attestations"] == 1

    # her session no longer works, and nothing personal remains
    assert client.get("/identity/users/me", headers=auth(w["alice"])).status_code == 401
    db = db_session_factory()
    try:
        assert db.get(User, w["alice_id"]) is None
        assert db.query(LedgerEntry).filter(LedgerEntry.user_id == w["alice_id"]).count() == 0
        assert db.query(DIDSession).filter(DIDSession.did == w["alice_did"]).count() == 0
        assert db.get(LedgerEntry, bob_entry).attester_subject == pseudonym(w["alice_did"])
        rec = db.query(DeletionRecord).one()
        assert w["alice_did"] not in str(rec.counts) and w["alice_id"] not in str(rec.counts)
    finally:
        db.close()

    # Bob's record is intact
    assert len(client.get(f"/ledger/entries/{bob_id}", headers=auth(bob)).json()) == 1
