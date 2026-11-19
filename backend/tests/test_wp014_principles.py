"""WP-014 "The Need" — the principles, made executable.

Each test asserts, against the running backend, one principle from the foundational
paper ``docs/publications/wp-014-the-need.md``. They add no new behaviour; they pin
safeguards that already exist to the paper that motivates them, so the standing test is
checked by CI rather than only promised in prose. The full principle -> code -> test
mapping is in ``docs/about/SAFEGUARDS_IN_CODE.md``.
"""

import pytest

from conftest import auth, create_profile, did_login, token_with_roles


@pytest.fixture()
def world(client, db_session_factory):
    alice_did, alice = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    _, bob = did_login(client)
    create_profile(client, bob, "Bob")
    att_did, _ = did_login(client)
    attester = token_with_roles(db_session_factory, att_did, ["can_attester"])
    rev_did, _ = did_login(client)
    reviewer = token_with_roles(db_session_factory, rev_did, ["can_user", "can_reviewer"])
    return {
        "alice": alice, "alice_id": alice_id, "alice_did": alice_did,
        "bob": bob, "attester": attester, "reviewer": reviewer,
    }


def _attest(client, token, user_id, value, ledger="reliability", metric="attendance"):
    r = client.post(
        "/ledger/entries",
        json={"user_id": user_id, "ledger_type": ledger, "metric": metric, "value": value, "evidence_ref": "ev"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# WP-014 §3-4 — Resolution: a claim is seen granularly and checked, not taken on narrative.
def test_resolution_scores_are_granular_and_checkable(client, world):
    w = world
    _attest(client, w["attester"], w["alice_id"], 1.0, ledger="contribution", metric="peer_validation")
    s = client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()
    exp = s["explanation"]
    # the reasoning travels with the score: a formula, and per-metric means and counts
    assert "formula" in exp
    assert exp["contribution"]["metrics"]["peer_validation"]["entries_counted"] == 1
    # a metric with no evidence shows as 0, not silently dropped — nothing hides in low resolution
    assert exp["contribution"]["metrics"]["usage_impact"]["mean"] == 0.0


# WP-014 §3 — Resolution tells the checkable from the merely asserted.
def test_resolution_self_reported_is_shown_not_counted(client, world):
    w = world
    for m in ["peer_validation", "usage_impact"]:
        client.post(
            "/ledger/entries",
            json={"ledger_type": "contribution", "metric": m, "value": 1.0},
            headers=auth(w["alice"]),
        )
    s = client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()
    assert s["overall_score"] == 0.0
    assert s["explanation"]["contribution"]["excluded_self_reported"] == 2


# WP-014 §5 — Re-valuation, not remembering: the past is revised, never overwritten.
def test_revaluation_corrections_supersede_never_overwrite(client, world):
    w = world
    entry = _attest(client, w["attester"], w["alice_id"], 0.2)
    before = client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()["reliability_score"]

    d = client.post(
        f"/ledger/entries/{entry}/disputes",
        json={"reason": "I attended", "proposed_value": 0.9},
        headers=auth(w["alice"]),
    ).json()
    # held to understand, not to sentence: the entry keeps counting while it is reconsidered
    s = client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()
    assert s["reliability_score"] == before
    assert s["explanation"]["entries_under_dispute"] == 1

    r = client.post(
        f"/ledger/disputes/{d['id']}/resolve",
        json={"outcome": "corrected", "note": "register checked", "corrected_value": 0.9},
        headers=auth(w["reviewer"]),
    ).json()
    entries = client.get(f"/ledger/entries/{w['alice_id']}", headers=auth(w["alice"])).json()
    old = next(e for e in entries if e["id"] == entry)
    new = next(e for e in entries if e["id"] == r["corrected_entry_id"])
    # the old value is not erased: it is marked superseded, and the new one points back to it
    assert old["status"] == "superseded"
    assert new["supersedes_id"] == entry and new["value"] == 0.9


# WP-014 §6 — Symmetric observation: no one-way view of another person.
def test_symmetric_observation_no_one_way_view(client, world):
    w = world
    req = client.post(
        "/allocation/requests",
        json={"pool": "housing", "description": "need"},
        headers=auth(w["alice"]),
    ).json()
    # Bob cannot see Alice's score, ledger or request, nor run a path from her
    assert client.get(f"/score/{w['alice_id']}", headers=auth(w["bob"])).status_code == 403
    assert client.get(f"/ledger/entries/{w['alice_id']}", headers=auth(w["bob"])).status_code == 403
    assert client.get(f"/allocation/requests/{req['id']}", headers=auth(w["bob"])).status_code == 403
    assert client.get(
        "/network/path", params={"to": "li:abc", "from": w["alice_id"]}, headers=auth(w["bob"])
    ).status_code == 403
    # but Alice sees her own — the eyes are equal, each over their own record
    assert client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).status_code == 200


# WP-014 §6 — The subject keeps the switch: disclosure and exit are the person's to control.
def test_subject_keeps_the_switch(client, world):
    w = world
    _attest(client, w["attester"], w["alice_id"], 1.0, ledger="contribution", metric="peer_validation")
    base = client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()["overall_score"]

    # consent is the person's to give...
    client.put("/identity/me/care-consent", json={"factors": ["health"]}, headers=auth(w["alice"]))
    _attest(client, w["attester"], w["alice_id"], 0.8, ledger="care", metric="health")
    assert client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()["overall_score"] > base

    # ...and the person's to withdraw: revoking deletes the data and never lowers priority
    r = client.put("/identity/me/care-consent", json={"factors": []}, headers=auth(w["alice"])).json()
    assert r["entries_deleted"] == 1
    after = client.get(f"/score/{w['alice_id']}", headers=auth(w["alice"])).json()["overall_score"]
    assert after == pytest.approx(base)

    # right of access: one document holds everything about them
    export = client.get("/identity/users/me/export", headers=auth(w["alice"])).json()
    assert export["profile"]["id"] == w["alice_id"]

    # exit is deliberate, never accidental: deletion refuses without explicit confirmation
    assert client.delete("/identity/users/me", headers=auth(w["alice"])).status_code == 400
