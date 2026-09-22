"""The work an integrating AI system actually does: search, map, revalue, maintain, exchange."""
import base64

import pytest
from nacl.signing import SigningKey

from conftest import auth, b64url, create_profile, did_login, new_did, token_with_roles

EVIDENCE = [
    ("identity", "units", 100, "title register"),
    ("revenue", "occupancy", 0.9, "rent roll"),
    ("revenue", "rent_per_unit_month", 1000, "rent roll"),
    ("assumption", "opex_ratio", 0.3, "budget"),
    ("assumption", "cap_rate", 0.05, "comparables"),
]


def agent_for(client, steward_token, scopes=("value.read", "value.derive")):
    did, sk = new_did()
    r = client.post("/agents/", json={"did": did, "name": "Valuation agent", "contact": "ops@example.org",
                                      "scopes": list(scopes)}, headers=auth(steward_token))
    assert r.status_code == 200, r.text
    ch = client.get("/auth/did/challenge").json()["challenge"]
    sig = sk.sign(ch.encode()).signature
    v = client.post("/agents/auth/verify", json={"did": did, "challenge": ch, "signature_b64url": b64url(sig)})
    return r.json(), v.json()["access_token"]


@pytest.fixture()
def world(client):
    _, holder = did_login(client)
    holder_id = create_profile(client, holder, "Holder")
    asset = client.post("/value/assets", json={"name": "Harbour Court", "kind": "residential"},
                        headers=auth(holder)).json()
    for category, key, value, ref in EVIDENCE:
        client.post(f"/value/assets/{asset['id']}/evidence",
                    json={"category": category, "key": key, "value": value, "evidence_ref": ref},
                    headers=auth(holder))
    agent, agent_token = agent_for(client, holder)
    return {"holder": holder, "holder_id": holder_id, "asset": asset["id"], "agent": agent, "token": agent_token}


# --- searching and mapping ----------------------------------------------------------

def test_agent_searches_what_its_steward_can_see(client, world):
    r = client.get("/value/search", params={"q": "harbour"}, headers=auth(world["token"])).json()
    assert r["count"] == 1
    row = r["assets"][0]
    assert row["id"] == world["asset"] and row["complete"] is True and row["value"] == 15120000.0

    # an agent gains no visibility of its own: another steward's agent sees nothing
    _, other = did_login(client)
    create_profile(client, other, "Other")
    _, other_agent = agent_for(client, other)
    assert client.get("/value/search", headers=auth(other_agent)).json()["count"] == 0


def test_search_filters_find_work(client, world):
    low = client.get("/value/search", params={"max_confidence": 0.1}, headers=auth(world["token"])).json()
    assert low["count"] == 1  # all evidence is self-reported, so confidence is 0
    client.post(f"/value/assets/{world['asset']}/evidence",
                json={"category": "carbon", "key": "carbon_tonnes_year", "value": 6000, "evidence_ref": "meter"},
                headers=auth(world["holder"]))
    client.post(f"/value/assets/{world['asset']}/evidence",
                json={"category": "assumption", "key": "carbon_price", "value": 150, "evidence_ref": "exchange"},
                headers=auth(world["holder"]))
    risky = client.get("/value/search", params={"liability_only": True}, headers=auth(world["token"])).json()
    assert risky["count"] == 1


def test_map_connects_asset_project_and_contributions(client, world):
    project = client.post("/bridge/projects", json={"name": "Harbour build", "target_amount": 1000000,
                                                    "asset_id": world["asset"]}, headers=auth(world["holder"])).json()
    c = client.post(f"/bridge/projects/{project['id']}/contributions",
                    json={"source_type": "in_kind", "description": "land", "offered_value": 250000,
                          "wants": "participation"}, headers=auth(world["holder"])).json()
    client.post(f"/bridge/contributions/{c['id']}/decision",
                json={"accept": True, "accepted_value": 250000, "valuation_basis": "valuation report"},
                headers=auth(world["holder"]))

    m = client.get(f"/value/assets/{world['asset']}/map", headers=auth(world["token"])).json()
    assert m["evidence_by_category"]["revenue"]["count"] == 2
    assert m["projects"][0]["id"] == project["id"]
    assert m["projects"][0]["contributions"]["value"] == 250000
    assert m["projects"][0]["contributions"]["by_source"] == {"in_kind": 250000}


# --- maintaining value ---------------------------------------------------------------

def test_work_queue_says_what_needs_doing(client, world):
    w = client.get("/value/work", headers=auth(world["token"])).json()
    types = {i["type"] for i in w["items"]}
    assert "low_confidence" in types and "never_assessed" in types
    assert all(i["suggested_action"] for i in w["items"])
    assert set(w["item_types"]) >= types

    client.post(f"/value/assets/{world['asset']}/assurance/run", headers=auth(world["holder"]))
    after = client.get("/value/work", headers=auth(world["token"])).json()
    assert "never_assessed" not in {i["type"] for i in after["items"]}


def test_missing_evidence_appears_as_work(client):
    _, holder = did_login(client)
    create_profile(client, holder, "Sparse")
    asset = client.post("/value/assets", json={"name": "Empty lot", "kind": "land"}, headers=auth(holder)).json()
    _, token = agent_for(client, holder)
    items = client.get("/value/work", headers=auth(token)).json()["items"]
    missing = [i for i in items if i["type"] == "missing_evidence"]
    assert {i["input"] for i in missing} >= {"units", "occupancy", "cap_rate"}
    assert asset["id"] == missing[0]["asset_id"]


# --- revaluing without attesting ------------------------------------------------------

def test_agent_proposes_a_revaluation_and_the_holder_decides(client, world):
    p = client.post(f"/value/assets/{world['asset']}/proposals",
                    json={"key": "occupancy", "value": 0.72, "source_ref": "letting report 2026-09",
                          "rationale": "Three units vacant since July."}, headers=auth(world["token"]))
    assert p.status_code == 201, p.text
    proposal = p.json()
    assert proposal["status"] == "open" and proposal["agent_id"] == world["agent"]["id"]

    # a proposal is not evidence: the value is unchanged until someone decides
    v = client.get(f"/value/assets/{world['asset']}/valuation", headers=auth(world["holder"])).json()
    assert v["inputs"]["occupancy"]["value"] == 0.9
    assert any(i["type"] == "open_proposal" for i in client.get("/value/work", headers=auth(world["holder"])).json()["items"])

    d = client.post(f"/value/proposals/{proposal['id']}/decision",
                    json={"accept": True, "note": "letting report checked"}, headers=auth(world["holder"])).json()
    assert d["status"] == "accepted" and d["evidence_id"]
    v2 = client.get(f"/value/assets/{world['asset']}/valuation", headers=auth(world["holder"])).json()
    assert v2["inputs"]["occupancy"]["value"] == 0.72
    # accepted by the holder, so it counts as self-reported, not attested
    assert v2["inputs"]["occupancy"]["status"] == "self_reported"


def test_attester_accepting_a_proposal_makes_it_attested(client, world, db_session_factory):
    did, _ = did_login(client)
    attester = token_with_roles(db_session_factory, did, ["can_user", "can_attester"])
    create_profile(client, attester, "Surveyor")
    proposal = client.post(f"/value/assets/{world['asset']}/proposals",
                           json={"key": "cap_rate", "value": 0.06, "source_ref": "market evidence"},
                           headers=auth(world["token"])).json()
    client.post(f"/value/proposals/{proposal['id']}/decision",
                json={"accept": True, "evidence_ref": "comparables pack 2026-09"}, headers=auth(attester))
    v = client.get(f"/value/assets/{world['asset']}/valuation", headers=auth(world["holder"])).json()
    assert v["inputs"]["cap_rate"]["status"] == "attested" and v["confidence"] > 0


def test_a_rejected_proposal_changes_nothing(client, world):
    proposal = client.post(f"/value/assets/{world['asset']}/proposals",
                           json={"key": "occupancy", "value": 0.1, "source_ref": "rumour"},
                           headers=auth(world["token"])).json()
    d = client.post(f"/value/proposals/{proposal['id']}/decision",
                    json={"accept": False, "note": "not supported"}, headers=auth(world["holder"])).json()
    assert d["status"] == "rejected"
    v = client.get(f"/value/assets/{world['asset']}/valuation", headers=auth(world["holder"])).json()
    assert v["inputs"]["occupancy"]["value"] == 0.9
    assert client.post(f"/value/proposals/{proposal['id']}/decision", json={"accept": True},
                       headers=auth(world["holder"])).status_code == 409


# --- exchange between nodes ------------------------------------------------------------

def test_document_round_trip_and_redaction(client, world):
    doc = client.get(f"/value/assets/{world['asset']}/document", headers=auth(world["token"])).json()
    assert doc["header"]["profile"] == "can.value.v1"
    assert len(doc["items"]) == 5 and doc["valuation"]["value"] == 15120000.0

    report = client.post("/value/documents/verify", json=doc, headers=auth(world["holder"])).json()
    assert report["valid"] and report["items"] == {"disclosed": 5, "withheld": 0}

    # redacted: revenue only, and it still verifies
    partial = client.get(f"/value/assets/{world['asset']}/document", params={"disclose": "revenue"},
                         headers=auth(world["token"])).json()
    assert {i.get("category") for i in partial["items"] if not i.get("withheld")} == {"revenue"}
    r2 = client.post("/value/documents/verify", json=partial, headers=auth(world["holder"])).json()
    assert r2["valid"] and r2["items"] == {"disclosed": 2, "withheld": 3}
    withheld = [i for i in partial["items"] if i.get("withheld")][0]
    assert "value" not in withheld and withheld["hash"]


def test_a_tampered_document_does_not_verify(client, world):
    doc = client.get(f"/value/assets/{world['asset']}/document", headers=auth(world["token"])).json()
    for item in doc["items"]:
        if item.get("key") == "occupancy":
            item["value"] = 0.99
    report = client.post("/value/documents/verify", json=doc, headers=auth(world["holder"])).json()
    assert report["valid"] is False and any("hash" in p for p in report["problems"])


def test_signed_documents_name_the_node(client, world, monkeypatch):
    from app.core.config import settings

    seed = SigningKey.generate()
    monkeypatch.setattr(settings, "NODE_SIGNING_KEY", base64.urlsafe_b64encode(bytes(seed)).decode().rstrip("="))
    monkeypatch.setattr(settings, "NODE_ID", "riyadh-node-1")
    node = client.get("/value/node").json()
    assert node["signing"] == "ed25519" and node["node_id"] == "riyadh-node-1"

    doc = client.get(f"/value/assets/{world['asset']}/document", headers=auth(world["token"])).json()
    report = client.post("/value/documents/verify", json=doc, headers=auth(world["holder"])).json()
    assert report["signed"] and report["signature_valid"] and report["signer_node"] == "riyadh-node-1"
    assert report["signer_trusted"] is False  # not in this node's trusted list

    doc["root"] = "0" * 64
    bad = client.post("/value/documents/verify", json=doc, headers=auth(world["holder"])).json()
    assert bad["valid"] is False


def test_importing_from_another_node_is_unverified_until_attested(client, world):
    doc = client.get(f"/value/assets/{world['asset']}/document", headers=auth(world["token"])).json()
    _, receiver = did_login(client)
    create_profile(client, receiver, "Receiver")
    r = client.post("/value/documents/import", json=doc, headers=auth(receiver)).json()
    assert r["imported_items"] == 5 and r["treated_as"] == "unverified"

    v = client.get(f"/value/assets/{r['asset_id']}/valuation", headers=auth(receiver)).json()
    assert v["complete"] and v["base"]["value"] == 15120000.0
    assert v["confidence"] == 0  # another node's word is not this node's evidence
    entry = client.get(f"/value/assets/{r['asset_id']}", headers=auth(receiver)).json()
    assert entry["evidence"][0]["evidence_ref"].startswith("node:")


def test_import_refuses_a_document_that_does_not_verify(client, world):
    doc = client.get(f"/value/assets/{world['asset']}/document", headers=auth(world["token"])).json()
    doc["items"][0]["value"] = 999
    _, receiver = did_login(client)
    create_profile(client, receiver, "Receiver2")
    assert client.post("/value/documents/import", json=doc, headers=auth(receiver)).status_code == 422
