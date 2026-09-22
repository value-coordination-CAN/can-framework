import pytest

from conftest import auth, create_profile, did_login


@pytest.fixture()
def people(client):
    _, sponsor = did_login(client)
    sponsor_id = create_profile(client, sponsor, "Sponsor")
    _, contributor = did_login(client)
    contributor_id = create_profile(client, contributor, "Contributor")
    _, supplier = did_login(client)
    supplier_id = create_profile(client, supplier, "Supplier")
    return {"sponsor": sponsor, "sponsor_id": sponsor_id, "contributor": contributor,
            "contributor_id": contributor_id, "supplier": supplier, "supplier_id": supplier_id}


def new_project(client, token, target=1_000_000.0, unit=1000.0):
    r = client.post("/bridge/projects", json={"name": "Regional development", "target_amount": target,
                                              "unit_value": unit, "currency": "USD"}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def contribute(client, token, pid, source_type, value, wants="participation", terms=None):
    return client.post(f"/bridge/projects/{pid}/contributions",
                       json={"source_type": source_type, "description": f"{source_type} contribution",
                             "offered_value": value, "wants": wants, "access_terms": terms},
                       headers=auth(token))


def accept(client, sponsor, cid, value=None, basis="valuation report"):
    return client.post(f"/bridge/contributions/{cid}/decision",
                       json={"accept": True, "accepted_value": value, "valuation_basis": basis, "note": "agreed"},
                       headers=auth(sponsor))


def test_wallet_starts_empty_with_three_layers(client, people):
    w = client.get("/bridge/wallet", headers=auth(people["sponsor"])).json()
    assert w["holdings"] == [] and w["layers"] == {}
    cfg = client.get("/bridge/config", headers=auth(people["sponsor"])).json()
    assert cfg["layers"] == ["fiat", "modernised_fiat", "direct_value"]
    # only the simulated rail is implemented; the rest are placeholders
    implemented = {r["name"] for r in cfg["rails"] if r["implemented"]}
    assert implemented == {"simulated"}
    assert {"instant_payment", "tokenised_deposit", "offline_value"} <= {r["name"] for r in cfg["rails"]}


def test_funding_mix_across_sources(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c1 = contribute(client, p["sponsor"], pid, "capital", 600_000).json()
    c2 = contribute(client, p["contributor"], pid, "in_kind", 250_000).json()
    c3 = contribute(client, p["contributor"], pid, "pre_committed_use", 150_000, wants="access",
                    terms={"right": "a workshop unit for five years"}).json()
    for c in (c1, c2, c3):
        assert accept(client, p["sponsor"], c["id"]).status_code == 200

    mix = client.get(f"/bridge/projects/{pid}", headers=auth(p["sponsor"])).json()["funding_mix"]
    assert mix["raised"] == 1_000_000 and mix["still_needed"] == 0
    assert mix["cash"] == 600_000 and mix["cash_share_pct"] == 60.0
    assert mix["cash_not_needed_pct"] == 40.0
    assert mix["by_source"]["in_kind"]["pct"] == 25.0
    assert mix["contributors"] == 2

    w = client.get("/bridge/wallet", headers=auth(p["contributor"])).json()
    kinds = {h["kind"]: h for h in w["holdings"]}
    assert kinds["participation_unit"]["amount"] == 250  # 250,000 / 1,000 per unit
    assert kinds["access_right"]["terms"] == {"right": "a workshop unit for five years"}
    assert w["layers"]["direct_value"]["count"] == 2


def test_only_sponsor_decides_and_valuation_can_differ(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c = contribute(client, p["contributor"], pid, "in_kind", 100_000).json()
    assert client.post(f"/bridge/contributions/{c['id']}/decision", json={"accept": True},
                       headers=auth(p["contributor"])).status_code == 403
    r = accept(client, p["sponsor"], c["id"], value=80_000).json()
    assert r["contribution"]["accepted_value"] == 80_000
    assert r["issued"][0]["amount"] == 80
    # the reviews a real deployment must record are surfaced, not assumed away
    assert any("valuation" in s for s in r["reviews_required"])
    assert accept(client, p["sponsor"], c["id"]).status_code == 409  # already decided


def test_supplier_paid_on_verified_delivery_with_future_proofed_profit(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    a = client.post(f"/bridge/projects/{pid}/suppliers",
                    json={"supplier_user_id": p["supplier_id"], "scope": "groundworks", "cash_share": 0.8},
                    headers=auth(p["sponsor"])).json()
    assert a["participation_share"] == pytest.approx(0.2)
    assert client.post(f"/bridge/agreements/{a['id']}/response", json={"accept": True}, headers=auth(p["supplier"])).json()["accepted_by_supplier"] == "accepted"

    inv = client.post(f"/bridge/agreements/{a['id']}/invoices",
                      json={"amount": 100_000, "description": "phase 1", "delivery_evidence_ref": "survey 2026-09"},
                      headers=auth(p["supplier"])).json()
    # unverified work cannot be paid
    assert client.post(f"/bridge/invoices/{inv['id']}/pay", headers=auth(p["sponsor"])).status_code == 409
    # the supplier cannot verify their own delivery
    assert client.post(f"/bridge/invoices/{inv['id']}/verify", json={"approve": True}, headers=auth(p["supplier"])).status_code == 403

    client.post(f"/bridge/invoices/{inv['id']}/verify", json={"approve": True}, headers=auth(p["sponsor"]))
    paid = client.post(f"/bridge/invoices/{inv['id']}/pay", headers=auth(p["sponsor"])).json()
    assert paid["cash_paid"] == 80_000 and paid["stake_value"] == 20_000
    assert paid["settlement"]["rail"] == "simulated" and paid["settlement"]["external_ref"].startswith("sim:")

    w = client.get("/bridge/wallet", headers=auth(p["supplier"])).json()
    kinds = {h["kind"]: h["amount"] for h in w["holdings"]}
    assert kinds["cash"] == 80_000 and kinds["participation_unit"] == 20


def test_declining_participation_means_all_cash(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    a = client.post(f"/bridge/projects/{pid}/suppliers",
                    json={"supplier_user_id": p["supplier_id"], "scope": "fit-out", "cash_share": 0.7},
                    headers=auth(p["sponsor"])).json()
    r = client.post(f"/bridge/agreements/{a['id']}/response", json={"accept": False}, headers=auth(p["supplier"])).json()
    assert r["cash_share"] == 1.0 and r["participation_share"] == 0.0


def test_pledge_without_sale_and_no_double_pledging(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c = contribute(client, p["contributor"], pid, "in_kind", 50_000).json()
    accept(client, p["sponsor"], c["id"])
    holding = client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"][0]
    assert holding["amount"] == 50

    r = client.post(f"/bridge/holdings/{holding['id']}/pledges", json={"amount": 30, "note": "working capital"},
                    headers=auth(p["contributor"]))
    assert r.status_code == 200
    again = client.post(f"/bridge/holdings/{holding['id']}/pledges", json={"amount": 30}, headers=auth(p["contributor"]))
    assert again.status_code == 409 and "double pledging" in again.json()["detail"]

    w = client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"][0]
    assert w["pledged"] == 30 and w["free"] == 20
    # the stake is still owned: it was not sold
    assert w["amount"] == 50

    client.delete(f"/bridge/pledges/{r.json()['id']}", headers=auth(p["contributor"]))
    assert client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"][0]["free"] == 50


def test_settle_direct_value_down_into_money(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c = contribute(client, p["contributor"], pid, "in_kind", 10_000).json()
    accept(client, p["sponsor"], c["id"])
    holding = client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"][0]

    client.post(f"/bridge/holdings/{holding['id']}/pledges", json={"amount": 8}, headers=auth(p["contributor"]))
    blocked = client.post(f"/bridge/holdings/{holding['id']}/settle", json={"amount": 5}, headers=auth(p["contributor"]))
    assert blocked.status_code == 409  # pledged value cannot be settled away

    ok = client.post(f"/bridge/holdings/{holding['id']}/settle", json={"amount": 2}, headers=auth(p["contributor"])).json()
    assert ok["cash"] == 2000 and ok["transfer"]["from_layer"] == "direct_value" and ok["transfer"]["to_layer"] == "fiat"
    w = {h["kind"]: h for h in client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"]}
    assert w["participation_unit"]["amount"] == 8 and w["cash"]["amount"] == 2000
    assert client.get("/bridge/transfers", headers=auth(p["contributor"])).json()[0]["rail"] == "simulated"


def test_access_rights_are_not_settled_for_cash(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c = contribute(client, p["contributor"], pid, "pre_committed_use", 30_000, wants="access",
                   terms={"right": "a home for ten years"}).json()
    accept(client, p["sponsor"], c["id"])
    h = [x for x in client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"] if x["kind"] == "access_right"][0]
    r = client.post(f"/bridge/holdings/{h['id']}/settle", json={"amount": 1}, headers=auth(p["contributor"]))
    assert r.status_code == 409 and "right to use" in r.json()["detail"]
    # but it can still be pledged as security
    assert client.post(f"/bridge/holdings/{h['id']}/pledges", json={"amount": 1}, headers=auth(p["contributor"])).status_code == 200


def test_others_cannot_touch_your_holdings(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c = contribute(client, p["contributor"], pid, "in_kind", 5_000).json()
    accept(client, p["sponsor"], c["id"])
    holding = client.get("/bridge/wallet", headers=auth(p["contributor"])).json()["holdings"][0]
    assert client.post(f"/bridge/holdings/{holding['id']}/pledges", json={"amount": 1}, headers=auth(p["supplier"])).status_code == 404
    assert client.post(f"/bridge/holdings/{holding['id']}/settle", json={"amount": 1}, headers=auth(p["supplier"])).status_code == 404


def test_wallet_exported_and_deleted_with_account(client, people):
    p = people
    pid = new_project(client, p["sponsor"])
    c = contribute(client, p["contributor"], pid, "in_kind", 20_000).json()
    accept(client, p["sponsor"], c["id"])

    data = client.get("/identity/users/me/export", headers=auth(p["contributor"])).json()
    assert data["wallet"]["holdings"][0]["kind"] == "participation_unit"
    assert len(data["wallet"]["contributions"]) == 1

    counts = client.delete("/identity/users/me", params={"confirm": "true"}, headers=auth(p["contributor"])).json()["counts"]
    assert counts["holdings"] == 1 and counts["contributions"] == 1
    # the sponsor's project survives
    assert client.get(f"/bridge/projects/{pid}", headers=auth(p["sponsor"])).status_code == 200
