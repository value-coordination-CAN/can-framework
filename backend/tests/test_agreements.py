"""From a committed introduction to a recorded stake: WP-012 joined to WP-010."""
import base64

import pytest
from nacl.signing import SigningKey

from app.core.config import settings
from app.value import forwarding
from app.value.commitments import commitment
from app.value.engine import load_value_config
from conftest import auth, create_profile, did_login, token_with_roles

QUERY = {"item_type": "capacity", "item_class": "covered_workshop", "region": "GCC-E", "period": "2027-Q1"}
ITEM = {"item_type": "capacity", "item_class": "covered_workshop", "title": "Two bays",
        "region": "GCC-E", "available_from": "2027-01-15", "discoverable": True}


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture()
def node(monkeypatch):
    key = SigningKey.generate()
    monkeypatch.setattr(settings, "NODE_ID", "node-a")
    monkeypatch.setattr(settings, "NODE_SIGNING_KEY", b64(bytes(key)))
    monkeypatch.setattr(load_value_config(), "discovery",
                        {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 120,
                         "max_degree_default": 3, "max_degree_limit": 6, "hop_decay": 0.6,
                         "peer_timeout_seconds": 1, "peer_max_queries_per_hour": 240})
    return key


@pytest.fixture()
def operator(client, db_session_factory):
    did, _ = did_login(client)
    token = token_with_roles(db_session_factory, did, ["can_user", "can_admin"])
    create_profile(client, token, "Operator")
    return token


def quiet_network(monkeypatch):
    sent = []

    def client_fn(peer, envelope, path="/map/peer/query"):
        sent.append({"peer": peer.node_id, "path": path, "body": envelope["body"]})
        return {"status": "pending"}

    monkeypatch.setattr(forwarding, "PEER_CLIENT", client_fn)
    return sent


def signed(key, from_node, body):
    return {"body": body, "from_node": from_node,
            "signature": b64(key.sign(forwarding.canonical(body)).signature)}


@pytest.fixture()
def agreed(client, node, operator, monkeypatch):
    """A committed introduction: an offer went out, the far end accepted, the asker committed."""
    key_b = SigningKey.generate()
    client.post("/map/peers", json={"node_id": "node-b", "public_key": b64(bytes(key_b.verify_key)),
                                    "base_url": "http://peer.invalid", "trust_weight": 0.8},
                headers=auth(operator))
    quiet_network(monkeypatch)
    _, asker = did_login(client)
    asker_id = create_profile(client, asker, "Boatbuilders")
    intro = client.post("/map/introductions", json={
        "paths": [["node-a", "node-b"]], **QUERY, "message": "We need covered space.",
        "offer": "Refit work in kind, 400 hours."}, headers=auth(asker)).json()
    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "reply_contact": "harbour@example.org", "reply_slice": None, "from_hop": 1}
    client.post("/map/peer/introduction/reply", json=signed(key_b, "node-b", reply))
    client.post(f"/map/introductions/{intro['id']}/commit",
                json={"contact": "boats@example.org", "note": "starting in January"}, headers=auth(asker))
    return {"asker": asker, "asker_id": asker_id, "intro": intro, "key_b": key_b}


# --- recording what was agreed --------------------------------------------------------------

def test_an_agreement_needs_a_commitment_first(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    client.post("/map/peers", json={"node_id": "node-b", "public_key": b64(bytes(key_b.verify_key)),
                                    "base_url": "http://peer.invalid"}, headers=auth(operator))
    quiet_network(monkeypatch)
    _, asker = did_login(client)
    create_profile(client, asker, "Asker")
    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "hello", "offer": "work"},
                        headers=auth(asker)).json()
    r = client.post(f"/map/introductions/{intro['id']}/agreement",
                    json={"kind": "contribution", "terms": "400 hours of refit work"}, headers=auth(asker))
    assert r.status_code == 409 and "committed" in r.json()["detail"]


def test_only_a_party_records_the_agreement(client, agreed):
    _, stranger = did_login(client)
    create_profile(client, stranger, "Stranger")
    r = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                    json={"kind": "contribution", "terms": "400 hours"}, headers=auth(stranger))
    assert r.status_code == 403


def test_the_agreement_is_recorded_and_verifiable(client, agreed):
    r = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                    json={"kind": "contribution", "terms": "400 hours of refit work over 18 months",
                          "value": 60000, "currency": "USD"}, headers=auth(agreed["asker"])).json()
    rec = r["agreement"]
    assert rec["kind"] == "contribution" and rec["value"] == 60000
    assert rec["counterpart_node"] == "node-b" and rec["counterpart_contact"] == "harbour@example.org"
    assert rec["offer"] == "Refit work in kind, 400 hours."  # what was offered is kept with it
    assert rec["status"] == "recorded" and r["created"] is None
    doc = rec["document"]
    assert doc["header"]["profile"] == "can.agreement.v1"
    assert client.post("/value/documents/verify", json=doc, headers=auth(agreed["asker"])).json()["valid"]
    assert "a stake is created there by a local party" in r["note"]


# --- becoming a stake, where both parties are here ---------------------------------------------

def test_an_agreement_between_local_parties_becomes_a_contribution(client, node, operator, monkeypatch):
    """The local case: the holder's project gains a contribution that earns participation."""
    key_b = SigningKey.generate()
    client.post("/map/peers", json={"node_id": "node-b", "public_key": b64(bytes(key_b.verify_key)),
                                    "base_url": "http://peer.invalid"}, headers=auth(operator))
    quiet_network(monkeypatch)
    _, asker = did_login(client)
    asker_id = create_profile(client, asker, "Boatbuilders")
    _, sponsor = did_login(client)
    create_profile(client, sponsor, "HarbourTrust")
    project = client.post("/bridge/projects", json={"name": "Harbour refit", "target_amount": 500000},
                          headers=auth(sponsor)).json()

    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "space for a refit", "offer": "400 hours of work"},
                        headers=auth(asker)).json()
    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "reply_contact": "harbour@example.org", "reply_slice": None, "from_hop": 1}
    client.post("/map/peer/introduction/reply", json=signed(key_b, "node-b", reply))
    client.post(f"/map/introductions/{intro['id']}/commit", json={"contact": "boats@example.org"},
                headers=auth(asker))

    # a party records what was agreed; the sponsor attaches it to their project
    rec = client.post(f"/map/introductions/{intro['id']}/agreement",
                      json={"kind": "contribution", "terms": "400 hours of refit work", "value": 60000,
                            "currency": "USD"}, headers=auth(asker)).json()["agreement"]
    r = client.post(f"/map/agreements/{rec['id']}/link",
                    json={"project_id": project["id"], "counterpart_user_id": asker_id},
                    headers=auth(sponsor)).json()
    assert r["created"]["source_type"] == "in_kind" and r["created"]["status"] == "proposed"
    assert r["agreement"]["status"] == "linked"

    # it is a real WP-010 contribution: the sponsor can accept it and it issues participation
    detail = client.get(f"/bridge/projects/{project['id']}", headers=auth(sponsor)).json()
    contribution = detail["contributions"][0]
    assert contribution["contributor_user_id"] == asker_id and contribution["offered_value"] == 60000
    accepted = client.post(f"/bridge/contributions/{contribution['id']}/decision",
                           json={"accept": True, "accepted_value": 60000,
                                 "valuation_basis": "agreed rate"}, headers=auth(sponsor)).json()
    assert accepted["issued"][0]["kind"] == "participation_unit" and accepted["issued"][0]["amount"] == 60
    wallet = client.get("/bridge/wallet", headers=auth(asker)).json()
    assert wallet["layers"]["direct_value"]["by_kind"]["participation_unit"] == 60


def test_an_access_agreement_becomes_pre_committed_use(client, agreed, operator):
    _, sponsor = did_login(client)
    create_profile(client, sponsor, "Sponsor")
    project = client.post("/bridge/projects", json={"name": "Quayside", "target_amount": 100000},
                          headers=auth(sponsor)).json()
    rec = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                      json={"kind": "access", "terms": "a bay for 18 months", "value": 30000},
                      headers=auth(agreed["asker"])).json()["agreement"]
    r = client.post(f"/map/agreements/{rec['id']}/link",
                    json={"project_id": project["id"], "counterpart_user_id": agreed["asker_id"]},
                    headers=auth(sponsor)).json()
    assert r["created"]["source_type"] == "pre_committed_use"
    detail = client.get(f"/bridge/projects/{project['id']}", headers=auth(sponsor)).json()
    assert detail["contributions"][0]["wants"] == "access"


def test_a_supply_agreement_becomes_a_supplier_agreement(client, agreed):
    _, sponsor = did_login(client)
    create_profile(client, sponsor, "Sponsor")
    project = client.post("/bridge/projects", json={"name": "Yard works", "target_amount": 200000},
                          headers=auth(sponsor)).json()
    rec = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                      json={"kind": "supply", "terms": "groundworks"},
                      headers=auth(agreed["asker"])).json()["agreement"]
    r = client.post(f"/map/agreements/{rec['id']}/link",
                    json={"project_id": project["id"], "counterpart_user_id": agreed["asker_id"],
                          "cash_share": 0.8}, headers=auth(sponsor)).json()
    assert r["created"]["cash_share"] == 0.8
    detail = client.get(f"/bridge/projects/{project['id']}", headers=auth(sponsor)).json()
    agreement = detail["supplier_agreements"][0]
    assert agreement["supplier_user_id"] == agreed["asker_id"]
    assert agreement["participation_share"] == pytest.approx(0.2)
    assert agreement["accepted_by_supplier"] == "pending"  # the supplier still chooses


def test_only_the_sponsor_attaches_an_agreement_to_a_project(client, agreed):
    _, sponsor = did_login(client)
    create_profile(client, sponsor, "Sponsor")
    project = client.post("/bridge/projects", json={"name": "Not yours", "target_amount": 1000},
                          headers=auth(sponsor)).json()
    rec = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                      json={"kind": "contribution", "terms": "work"},
                      headers=auth(agreed["asker"])).json()["agreement"]
    r = client.post(f"/map/agreements/{rec['id']}/link",
                    json={"project_id": project["id"], "counterpart_user_id": agreed["asker_id"]},
                    headers=auth(agreed["asker"]))
    assert r.status_code == 403 and "sponsor" in r.json()["detail"]


def test_an_agreement_links_once(client, agreed):
    _, sponsor = did_login(client)
    create_profile(client, sponsor, "Sponsor")
    project = client.post("/bridge/projects", json={"name": "Yard", "target_amount": 1000},
                          headers=auth(sponsor)).json()
    rec = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                      json={"kind": "contribution", "terms": "work", "value": 10},
                      headers=auth(agreed["asker"])).json()["agreement"]
    client.post(f"/map/agreements/{rec['id']}/link",
                json={"project_id": project["id"], "counterpart_user_id": agreed["asker_id"]},
                headers=auth(sponsor))
    again = client.post(f"/map/agreements/{rec['id']}/link",
                        json={"project_id": project["id"], "counterpart_user_id": agreed["asker_id"]},
                        headers=auth(sponsor))
    assert again.status_code == 422 and "already linked" in again.json()["detail"]


# --- the other node's copy ---------------------------------------------------------------------

def test_the_other_node_imports_the_agreement_and_links_it_itself(client, agreed):
    doc = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                      json={"kind": "contribution", "terms": "400 hours of refit work", "value": 60000,
                            "currency": "USD"}, headers=auth(agreed["asker"])).json()["agreement"]["document"]

    _, other = did_login(client)
    create_profile(client, other, "OtherSide")
    imported = client.post("/map/agreements/import", json=doc, headers=auth(other)).json()
    assert imported["verification"]["valid"] and imported["agreement"]["terms"] == "400 hours of refit work"
    assert imported["agreement"]["status"] == "recorded"      # a record, not yet a stake
    assert imported["agreement"]["linked_id"] is None

    # it becomes a stake only when a local party attaches it to a local project
    project = client.post("/bridge/projects", json={"name": "Their yard", "target_amount": 1000},
                          headers=auth(other)).json()
    _, worker = did_login(client)
    worker_id = create_profile(client, worker, "LocalWorker")
    linked = client.post(f"/map/agreements/{imported['agreement']['id']}/link",
                         json={"project_id": project["id"], "counterpart_user_id": worker_id},
                         headers=auth(other)).json()
    assert linked["created"]["contribution_id"] and linked["agreement"]["status"] == "linked"


def test_a_tampered_agreement_document_is_refused(client, agreed):
    doc = client.post(f"/map/introductions/{agreed['intro']['id']}/agreement",
                      json={"kind": "contribution", "terms": "400 hours", "value": 60000},
                      headers=auth(agreed["asker"])).json()["agreement"]["document"]
    doc["agreement"]["value"] = 6_000_000
    _, other = did_login(client)
    create_profile(client, other, "OtherSide")
    assert client.post("/map/agreements/import", json=doc, headers=auth(other)).status_code == 422
