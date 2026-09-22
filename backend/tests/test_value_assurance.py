import pytest

from app.value.engine import apply_changes, value_from
from conftest import auth, create_profile, did_login, token_with_roles

EXAMPLE = {
    "units": ("identity", 100),
    "occupancy": ("revenue", 0.9),
    "rent_per_unit_month": ("revenue", 1000),
    "opex_ratio": ("assumption", 0.3),
    "cap_rate": ("assumption", 0.05),
}


@pytest.fixture()
def holder(client):
    _, token = did_login(client)
    uid = create_profile(client, token, "Holder")
    asset = client.post("/value/assets", json={"name": "Harbour Court", "kind": "residential"}, headers=auth(token)).json()
    return token, uid, asset["id"]


def add(client, token, asset_id, key, value, ref=None, category=None):
    cat = category or EXAMPLE.get(key, ("identity", None))[0]
    return client.post(
        f"/value/assets/{asset_id}/evidence",
        json={"category": cat, "key": key, "value": value, "evidence_ref": ref},
        headers=auth(token),
    )


def fill(client, token, asset_id, ref=None):
    for k, (_, v) in EXAMPLE.items():
        assert add(client, token, asset_id, k, v, ref).status_code == 200


def test_income_model_arithmetic():
    v = {"units": 100, "occupancy": 0.9, "rent_per_unit_month": 1000, "opex_ratio": 0.3, "cap_rate": 0.05,
         "capex_to_complete": 0, "carbon_tonnes_year": 0, "carbon_price": 0}
    r = value_from(v)
    assert r["gross_income"] == 1_080_000
    assert r["net_operating_income"] == pytest.approx(756_000)
    assert r["value"] == pytest.approx(15_120_000)
    assert not r["is_liability"]
    # scenario changes respect bounds
    assert apply_changes(v, {"occupancy": {"mul": 2}})["occupancy"] == 1


def test_valuation_needs_evidence_then_explains(client, holder):
    token, _, aid = holder
    v = client.get(f"/value/assets/{aid}/valuation", headers=auth(token)).json()
    assert v["complete"] is False and "units" in v["missing_inputs"]

    fill(client, token, aid)
    v = client.get(f"/value/assets/{aid}/valuation", headers=auth(token)).json()
    assert v["complete"] and v["base"]["value"] == pytest.approx(15_120_000)
    assert v["confidence"] == 0  # all self-reported
    assert set(v["scenarios"]) >= {"wage_shock", "severe_wage_shock", "energy_carbon_shock", "rate_rise", "combined_stress"}
    assert all(s["value"] < v["base"]["value"] for s in v["scenarios"].values())
    assert any("attested evidence" in line for line in v["explanation"])


def test_attested_evidence_raises_confidence_and_supersedes(client, holder, db_session_factory):
    token, _, aid = holder
    fill(client, token, aid)
    did, _ = did_login(client)
    attester = token_with_roles(db_session_factory, did, ["can_attester"])
    assert add(client, attester, aid, "occupancy", 0.8).status_code == 422  # evidence_ref required
    assert add(client, attester, aid, "occupancy", 0.8, ref="rent roll Sept").status_code == 200
    v = client.get(f"/value/assets/{aid}/valuation", headers=auth(token)).json()
    assert v["inputs"]["occupancy"]["status"] == "attested" and v["inputs"]["occupancy"]["value"] == 0.8
    assert v["confidence"] == pytest.approx(0.25)
    history = client.get(f"/value/assets/{aid}/evidence/history", headers=auth(token)).json()
    occ = [e for e in history if e["key"] == "occupancy"]
    assert len(occ) == 2 and sum(1 for e in occ if e["superseded_at"] is None) == 1


def test_evidence_validation(client, holder):
    token, _, aid = holder
    assert add(client, token, aid, "occupancy", 1.5).status_code == 422
    assert add(client, token, aid, "occupancy", 0.5, category="identity").status_code == 422
    r = client.post(f"/value/assets/{aid}/evidence", json={"category": "contribution", "key": "local_hiring", "text": "40% local staff"}, headers=auth(token))
    assert r.status_code == 200


def test_value_turns_into_liability(client, holder):
    token, _, aid = holder
    fill(client, token, aid)
    add(client, token, aid, "carbon_tonnes_year", 5000, category="carbon")
    add(client, token, aid, "carbon_price", 120, category="assumption")
    v = client.get(f"/value/assets/{aid}/valuation", headers=auth(token)).json()
    assert not v["base"]["is_liability"]
    assert v["scenarios"]["combined_stress"]["is_liability"]
    assert any("turns into liability" in line for line in v["explanation"])


def test_agent_loop_respects_mandate(client, holder):
    token, _, aid = holder
    fill(client, token, aid)

    run1 = client.post(f"/value/assets/{aid}/assurance/run", headers=auth(token)).json()
    assert run1["steps"]["detect"]["first_run"] is True
    assert run1["actions"] and not any(a["taken"] for a in run1["actions"])  # no mandate yet
    assert all(a["why_not"] == "no active mandate" for a in run1["actions"])

    r = client.put(f"/value/assets/{aid}/mandate", json={"enabled": True, "alert_drop_pct": 5, "min_confidence": 0.6,
                                                         "flag_liability": True, "allowed_actions": ["alert"]}, headers=auth(token))
    assert r.status_code == 200
    add(client, token, aid, "occupancy", 0.7)  # a fall in occupancy
    run2 = client.post(f"/value/assets/{aid}/assurance/run", headers=auth(token)).json()
    changes = run2["steps"]["detect"]["changes"]
    assert [c["input"] for c in changes] == ["occupancy"]
    assert run2["steps"]["interpret"]["effects"]["occupancy"] < 0
    taken = [a for a in run2["actions"] if a["taken"]]
    assert taken and taken[0]["type"] == "alert" and "fell" in taken[0]["message"]
    # request_attestation is recommended but not in the mandate, so not taken
    assert any(a["type"] == "request_attestation" and not a["taken"] for a in run2["actions"])

    assert client.put(f"/value/assets/{aid}/mandate", json={"enabled": True, "allowed_actions": ["transfer"]}, headers=auth(token)).status_code == 422
    runs = client.get(f"/value/assets/{aid}/assurance/runs", headers=auth(token)).json()
    assert len(runs) == 2


def test_selective_disclosure(client, holder):
    token, _, aid = holder
    fill(client, token, aid)
    _, lender = did_login(client)
    lender_id = create_profile(client, lender, "Lender")

    assert client.get(f"/value/assets/{aid}/valuation", headers=auth(lender)).status_code == 403
    r = client.put(f"/value/assets/{aid}/shares", json={"grantee_user_id": lender_id, "categories": ["revenue", "valuation"]}, headers=auth(token))
    assert r.status_code == 200

    listed = client.get("/value/assets", headers=auth(lender)).json()
    assert listed["shared_with_me"][0]["id"] == aid
    detail = client.get(f"/value/assets/{aid}", headers=auth(lender)).json()
    assert {e["category"] for e in detail["evidence"]} == {"revenue"} and detail["mandate"] is None
    v = client.get(f"/value/assets/{aid}/valuation", headers=auth(lender)).json()
    assert v["complete"] and set(v["inputs"]) == {"occupancy", "rent_per_unit_month"}
    # the lender cannot act on the asset
    assert client.post(f"/value/assets/{aid}/assurance/run", headers=auth(lender)).status_code == 403
    assert add(client, lender, aid, "occupancy", 0.1).status_code == 403
    assert client.get(f"/value/assets/{aid}/assurance/runs", headers=auth(lender)).status_code == 403

    client.delete(f"/value/assets/{aid}/shares/{lender_id}", headers=auth(token))
    assert client.get(f"/value/assets/{aid}/valuation", headers=auth(lender)).status_code == 403


def test_assets_exported_and_deleted_with_account(client, holder):
    token, _, aid = holder
    fill(client, token, aid)
    client.post(f"/value/assets/{aid}/assurance/run", headers=auth(token))
    data = client.get("/identity/users/me/export", headers=auth(token)).json()
    assert data["assets"][0]["id"] == aid and len(data["assets"][0]["evidence"]) == 5
    counts = client.delete("/identity/users/me", params={"confirm": "true"}, headers=auth(token)).json()["counts"]
    assert counts["assets"] == 1


def test_ui_is_served(client):
    r = client.get("/ui/")
    assert r.status_code == 200 and "Value Assurance" in r.text
    assert client.get("/ui/app.js").status_code == 200
