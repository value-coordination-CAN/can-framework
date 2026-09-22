"""WP-012 steps 1 and 2: shareable map slices, and commitment discovery."""
import pytest

from app.value.commitments import commitment, current_epoch
from app.value.engine import load_value_config
from conftest import auth, create_profile, did_login

WORKSHOP = {
    "item_type": "capacity", "item_class": "covered_workshop", "title": "Two bays at Harbour Court",
    "quantity": 2, "unit": "bays", "region": "GCC-E", "available_from": "2027-01-15",
    "description": "Covered, water access, three-phase power.",
}
NEED = {**WORKSHOP, "item_type": "need", "title": "Covered space for a refit", "description": "18 months."}


@pytest.fixture()
def holder(client):
    _, token = did_login(client)
    uid = create_profile(client, token, "Holder")
    return token, uid


def add_item(client, token, payload, discoverable=True):
    r = client.post("/map/items", json={**payload, "discoverable": discoverable}, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


# --- needs and capacities -------------------------------------------------------------

def test_record_what_you_have_spare_and_what_you_lack(client, holder):
    token, _ = holder
    cap = add_item(client, token, WORKSHOP)
    need = add_item(client, token, NEED, discoverable=False)
    assert cap["item_type"] == "capacity" and need["discoverable"] is False
    mine = client.get("/map/items", headers=auth(token)).json()
    assert {i["id"] for i in mine} == {cap["id"], need["id"]}
    assert len(client.get("/map/items", params={"item_type": "need"}, headers=auth(token)).json()) == 1


def test_discoverability_is_opt_in_and_reversible(client, holder):
    token, _ = holder
    item = add_item(client, token, WORKSHOP, discoverable=False)
    c = client.get(f"/map/items/{item['id']}/commitment", headers=auth(token)).json()
    assert c["discoverable"] is False
    # coarse attributes only: nothing about quantity, description or the exact site
    assert set(c["coarse_attributes"]) == {"item_type", "item_class", "region", "period"}
    assert c["coarse_attributes"]["period"] == "2027-Q1"

    client.patch(f"/map/items/{item['id']}", json={"discoverable": True}, headers=auth(token))
    assert client.get(f"/map/items/{item['id']}/commitment", headers=auth(token)).json()["discoverable"] is True
    client.patch(f"/map/items/{item['id']}", json={"status": "closed"}, headers=auth(token))
    assert client.get("/map/items", headers=auth(token)).json()[0]["status"] == "closed"


def test_only_the_holder_touches_their_items(client, holder):
    token, _ = holder
    item = add_item(client, token, WORKSHOP)
    _, other = did_login(client)
    create_profile(client, other, "Other")
    assert client.patch(f"/map/items/{item['id']}", json={"status": "closed"}, headers=auth(other)).status_code == 404
    assert client.delete(f"/map/items/{item['id']}", headers=auth(other)).status_code == 404


# --- commitment discovery -------------------------------------------------------------

def test_a_searcher_can_form_the_same_commitment(client, holder):
    token, _ = holder
    terms = client.get("/map/discovery").json()  # public: no account needed to learn the rules
    assert terms["attributes"] == ["item_type", "item_class", "region", "period"]
    item = add_item(client, token, WORKSHOP)
    mine = client.get(f"/map/items/{item['id']}/commitment", headers=auth(token)).json()
    assert mine["commitment"] == commitment("capacity", "covered_workshop", "GCC-E", "2027-Q1")
    assert mine["epoch"] == current_epoch() == terms["epoch"]


def test_match_or_no_match_and_nothing_else(client, holder, monkeypatch):
    monkeypatch.setattr(load_value_config(), "discovery", {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 120})
    token, _ = holder
    add_item(client, token, WORKSHOP)
    _, searcher = did_login(client)
    create_profile(client, searcher, "Searcher")

    hit = client.post("/map/query", json={"item_type": "capacity", "item_class": "covered_workshop",
                                          "region": "GCC-E", "period": "2027-Q1"}, headers=auth(searcher)).json()
    assert hit["match"] is True and hit["node_id"]
    # the answer carries no contents, no identities, no quantity
    body = str(hit)
    assert "Harbour" not in body and "bays" not in body and "three-phase" not in body

    miss = client.post("/map/query", json={"item_type": "capacity", "item_class": "cold_storage",
                                           "region": "GCC-E", "period": "2027-Q1"}, headers=auth(searcher)).json()
    assert miss["match"] is False and miss["node_id"] is None


def test_k_anonymity_stops_a_match_pointing_at_one_item(client, holder, monkeypatch):
    monkeypatch.setattr(load_value_config(), "discovery", {"k_anonymity": 2, "epoch_days": 7, "max_queries_per_hour": 120})
    token, _ = holder
    add_item(client, token, WORKSHOP)
    _, searcher = did_login(client)
    create_profile(client, searcher, "Searcher")
    q = {"item_type": "capacity", "item_class": "covered_workshop", "region": "GCC-E", "period": "2027-Q1"}
    assert client.post("/map/query", json=q, headers=auth(searcher)).json()["match"] is False

    _, second = did_login(client)
    create_profile(client, second, "SecondHolder")
    add_item(client, second, {**WORKSHOP, "title": "One bay elsewhere"})
    assert client.post("/map/query", json=q, headers=auth(searcher)).json()["match"] is True


def test_items_that_are_not_discoverable_never_match(client, holder, monkeypatch):
    monkeypatch.setattr(load_value_config(), "discovery", {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 120})
    token, _ = holder
    add_item(client, token, WORKSHOP, discoverable=False)
    _, searcher = did_login(client)
    create_profile(client, searcher, "Searcher")
    q = {"item_type": "capacity", "item_class": "covered_workshop", "region": "GCC-E", "period": "2027-Q1"}
    assert client.post("/map/query", json=q, headers=auth(searcher)).json()["match"] is False


def test_queries_are_rate_limited(client, holder, monkeypatch):
    monkeypatch.setattr(load_value_config(), "discovery", {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 3})
    token, _ = holder
    add_item(client, token, WORKSHOP)
    q = {"item_type": "capacity", "item_class": "covered_workshop", "region": "GCC-E", "period": "2027-Q1"}
    codes = [client.post("/map/query", json=q, headers=auth(token)).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429


def test_local_matching_finds_the_need_next_door(client, holder, monkeypatch):
    monkeypatch.setattr(load_value_config(), "discovery", {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 120})
    token, _ = holder
    capacity = add_item(client, token, WORKSHOP)
    _, cooperative = did_login(client)
    create_profile(client, cooperative, "Boatbuilders")
    add_item(client, cooperative, NEED)

    r = client.get(f"/map/matches/{capacity['id']}", headers=auth(token)).json()
    assert r["looking_for"] == "need" and r["matches_on_this_node"] == 1
    assert "title" not in str(r)


# --- shareable slices ------------------------------------------------------------------

def test_slice_is_verifiable_and_redactable(client, holder):
    token, _ = holder
    add_item(client, token, WORKSHOP)
    add_item(client, token, NEED)
    asset = client.post("/value/assets", json={"name": "Harbour Court", "kind": "residential"},
                        headers=auth(token)).json()
    client.post(f"/value/assets/{asset['id']}/evidence",
                json={"category": "identity", "key": "units", "value": 120, "evidence_ref": "title"},
                headers=auth(token))

    doc = client.post("/map/slice", json={"asset_ids": [asset["id"]], "purpose": "introduction to a lender"},
                      headers=auth(token)).json()
    assert doc["header"]["profile"] == "can.map.v1" and len(doc["items"]) == 3
    report = client.post("/value/documents/verify", json=doc, headers=auth(token)).json()
    assert report["valid"] and report["items"] == {"disclosed": 3, "withheld": 0}

    # share capacities only: needs and assets are withheld, and it still verifies
    partial = client.post("/map/slice", json={"asset_ids": [asset["id"]], "include": ["capacity"]},
                          headers=auth(token)).json()
    r2 = client.post("/value/documents/verify", json=partial, headers=auth(token)).json()
    assert r2["valid"] and r2["items"] == {"disclosed": 1, "withheld": 2}
    disclosed = [i for i in partial["items"] if not i.get("withheld")][0]
    assert disclosed["item_type"] == "capacity" and "Harbour Court" not in str(
        [i for i in partial["items"] if i.get("withheld")])


def test_a_tampered_slice_does_not_verify(client, holder):
    token, _ = holder
    add_item(client, token, WORKSHOP)
    doc = client.post("/map/slice", json={}, headers=auth(token)).json()
    doc["items"][0]["quantity"] = 99
    report = client.post("/value/documents/verify", json=doc, headers=auth(token)).json()
    assert report["valid"] is False


def test_you_cannot_share_what_is_not_yours(client, holder):
    token, _ = holder
    _, other = did_login(client)
    create_profile(client, other, "Other")
    theirs = client.post("/value/assets", json={"name": "Theirs", "kind": "land"}, headers=auth(other)).json()
    r = client.post("/map/slice", json={"asset_ids": [theirs["id"]]}, headers=auth(token))
    assert r.status_code == 403
