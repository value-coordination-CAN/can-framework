"""WP-012 step 5: introductions. A path says a match exists; this is how the ends meet.

Every hop may refuse, and nobody is contactable merely for being on a graph.
"""
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
    monkeypatch.setattr(load_value_config(), "introductions",
                        {"ttl_hours": 72, "max_message_chars": 500, "max_open_per_caller": 3})
    return key


@pytest.fixture()
def operator(client, db_session_factory):
    did, _ = did_login(client)
    token = token_with_roles(db_session_factory, did, ["can_user", "can_admin"])
    create_profile(client, token, "Operator")
    return token


def add_peer(client, admin_token, node_id, public_key, base_url="http://peer.invalid"):
    r = client.post("/map/peers", json={"node_id": node_id, "public_key": public_key,
                                        "base_url": base_url, "trust_weight": 0.8},
                    headers=auth(admin_token))
    assert r.status_code == 201, r.text
    return r.json()


def capture_network(monkeypatch, answers=None):
    """Record what this node hands to its peers, and reply as a peer would."""
    sent = []

    def client(peer, envelope, path="/map/peer/query"):
        sent.append({"peer": peer.node_id, "path": path, "body": envelope["body"]})
        return (answers or {}).get(path, {"status": "pending"})

    monkeypatch.setattr(forwarding, "PEER_CLIENT", client)
    return sent


def signed_envelope(key, from_node, body):
    return {"body": body, "from_node": from_node,
            "signature": b64(key.sign(forwarding.canonical(body)).signature)}


# --- asking ------------------------------------------------------------------------------

def test_an_introduction_travels_to_the_next_hop(client, node, operator, monkeypatch):
    add_peer(client, operator, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    sent = capture_network(monkeypatch)
    r = client.post("/map/introductions", json={
        "paths": [["node-a", "node-b", "node-c"]], **QUERY,
        "message": "We need covered space for an 18-month refit.",
        "offer": "Refit work in kind, or rent, whichever suits."},
        headers=auth(operator))
    assert r.status_code == 201, r.text
    intro = r.json()
    assert intro["role"] == "origin" and intro["status"] == "forwarded"
    # it went to the next hop only, carrying the message and the path, not our identity
    assert sent[0]["peer"] == "node-b" and sent[0]["path"] == "/map/peer/introduction"
    assert sent[0]["body"]["hop_index"] == 1 and "refit" in sent[0]["body"]["message"]
    assert "requested_by" not in sent[0]["body"]


def test_a_path_must_start_here_and_not_repeat(client, node, operator, monkeypatch):
    capture_network(monkeypatch)
    bad = client.post("/map/introductions", json={"paths": [["node-z", "node-b"]], **QUERY, "message": "hello", "offer": "work"},
                      headers=auth(operator))
    assert bad.status_code == 422 and "start at this node" in bad.json()["detail"]
    loop = client.post("/map/introductions", json={"paths": [["node-a", "node-b", "node-a"]], **QUERY,
                                                   "message": "hello", "offer": "work"}, headers=auth(operator))
    assert loop.status_code == 422 and "twice" in loop.json()["detail"]


def test_an_unreachable_next_hop_is_reported_not_hidden(client, node, operator):
    r = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY, "message": "hello", "offer": "work"},
                    headers=auth(operator)).json()
    assert r["status"] == "declined" and r["blocked_by"] == "node-b"
    assert "not a peer" in r["routes"][0]["note"]


def test_open_introductions_are_capped(client, node, operator, monkeypatch):
    add_peer(client, operator, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    capture_network(monkeypatch)
    body = {"paths": [["node-a", "node-b"]], **QUERY, "message": "hello", "offer": "work"}
    codes = [client.post("/map/introductions", json=body, headers=auth(operator)).status_code for _ in range(4)]
    assert codes == [201, 201, 201, 429]


# --- relaying ------------------------------------------------------------------------------

def test_a_relay_carries_an_offer_without_being_asked(client, node, operator, monkeypatch):
    """An offer travels to the far end by itself: relays do not gate it."""
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    add_peer(client, operator, "node-c", b64(bytes(SigningKey.generate().verify_key)))
    sent = capture_network(monkeypatch)

    body = {"correlation_id": "c1", "commitment": commitment(**QUERY), "offer": "refit work in kind",
            "path": ["node-b", "node-a", "node-c"], "hop_index": 1, "message": "please pass this on"}
    r = client.post("/map/peer/introduction", json=signed_envelope(key_b, "node-b", body))
    assert r.status_code == 200 and r.json()["role"] == "relay" and r.json()["status"] == "forwarded"

    onward = [s for s in sent if s["path"] == "/map/peer/introduction"][-1]
    assert onward["peer"] == "node-c" and onward["body"]["hop_index"] == 2
    assert onward["body"]["offer"] == "refit work in kind"  # the offer travels intact


def test_an_operator_who_reviews_is_seen_to_hold_things_up(client, node, operator, monkeypatch):
    """A node may review each request. Then it is visibly the one holding it."""
    monkeypatch.setattr(load_value_config(), "introductions",
                        {"ttl_hours": 72, "max_message_chars": 500, "max_open_per_caller": 3,
                         "relay_policy": "review", "connection_weight_gain": 0.05})
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    add_peer(client, operator, "node-c", b64(bytes(SigningKey.generate().verify_key)))
    sent = capture_network(monkeypatch)
    body = {"correlation_id": "c2", "commitment": commitment(**QUERY), "offer": "rent",
            "path": ["node-b", "node-a", "node-c"], "hop_index": 1, "message": "pass it on"}
    client.post("/map/peer/introduction", json=signed_envelope(key_b, "node-b", body))
    intro = [i for i in client.get("/map/introductions", headers=auth(operator)).json()
             if i["correlation_id"] == "c2"][0]
    assert intro["status"] == "pending" and intro["awaiting_you"] is True

    _, ordinary = did_login(client)
    create_profile(client, ordinary, "Ordinary")
    assert client.post(f"/map/introductions/{intro['id']}/decision", json={"accept": True},
                       headers=auth(ordinary)).status_code == 403

    d = client.post(f"/map/introductions/{intro['id']}/decision",
                    json={"accept": False, "note": "not a request we will carry"}, headers=auth(operator)).json()
    assert d["status"] == "declined" and d["blocked_by"] == "node-a"  # named, in its own name
    reply = [s for s in sent if s["path"] == "/map/peer/introduction/reply"][-1]
    assert reply["body"]["status"] == "declined" and reply["body"]["blocked_by"] == "node-a"
    assert reply["body"]["reply_contact"] is None  # a refusal carries no contact


# --- the far end ---------------------------------------------------------------------------

def test_the_holder_decides_and_an_acceptance_carries_contact_and_a_slice(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    _, holder = did_login(client)
    create_profile(client, holder, "Holder")
    item = client.post("/map/items", json=ITEM, headers=auth(holder)).json()
    sent = capture_network(monkeypatch)

    body = {"correlation_id": "c3", "commitment": commitment(**QUERY),
            "path": ["node-b", "node-a"], "hop_index": 1, "message": "Boatbuilders need covered space."}
    r = client.post("/map/peer/introduction", json=signed_envelope(key_b, "node-b", body)).json()
    assert r["role"] == "destination"

    # the holder of the matching item sees it waiting; a stranger does not
    mine = [i for i in client.get("/map/introductions", headers=auth(holder)).json() if i["correlation_id"] == "c3"]
    assert mine and mine[0]["awaiting_you"] is True and mine[0]["candidate_items"] == [item["id"]]
    _, stranger = did_login(client)
    create_profile(client, stranger, "Stranger")
    assert [i for i in client.get("/map/introductions", headers=auth(stranger)).json()
            if i["correlation_id"] == "c3"] == []
    assert client.post(f"/map/introductions/{mine[0]['id']}/decision", json={"accept": True,
                       "reply_contact": "x@example.org"}, headers=auth(stranger)).status_code == 403

    # accepting means choosing how to be reached
    no_contact = client.post(f"/map/introductions/{mine[0]['id']}/decision", json={"accept": True},
                             headers=auth(holder))
    assert no_contact.status_code == 409 and "way to be reached" in no_contact.json()["detail"]

    d = client.post(f"/map/introductions/{mine[0]['id']}/decision",
                    json={"accept": True, "reply_contact": "harbour@example.org", "share_items": [item["id"]]},
                    headers=auth(holder)).json()
    assert d["status"] == "accepted"
    reply = [s for s in sent if s["path"] == "/map/peer/introduction/reply"][-1]
    assert reply["peer"] == "node-b" and reply["body"]["reply_contact"] == "harbour@example.org"
    # the acceptance carries a verifiable slice of exactly what the holder chose
    sl = reply["body"]["reply_slice"]
    assert sl["header"]["profile"] == "can.map.v1"
    assert client.post("/value/documents/verify", json=sl, headers=auth(holder)).json()["valid"]


def test_you_can_only_share_your_own_items(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    _, holder = did_login(client)
    create_profile(client, holder, "Holder")
    client.post("/map/items", json=ITEM, headers=auth(holder))
    _, other = did_login(client)
    create_profile(client, other, "Other")
    theirs = client.post("/map/items", json={**ITEM, "title": "Someone else's bay"}, headers=auth(other)).json()
    capture_network(monkeypatch)

    body = {"correlation_id": "c4", "commitment": commitment(**QUERY),
            "path": ["node-b", "node-a"], "hop_index": 1, "message": "hello"}
    client.post("/map/peer/introduction", json=signed_envelope(key_b, "node-b", body))
    mine = [i for i in client.get("/map/introductions", headers=auth(holder)).json()
            if i["correlation_id"] == "c4"][0]
    r = client.post(f"/map/introductions/{mine['id']}/decision",
                    json={"accept": True, "reply_contact": "a@example.org", "share_items": [theirs["id"]]},
                    headers=auth(holder))
    assert r.status_code == 403


# --- replies coming back --------------------------------------------------------------------

def test_an_acceptance_reaches_the_person_who_asked(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    capture_network(monkeypatch)
    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "hello", "offer": "work"}, headers=auth(operator)).json()

    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "decision_note": "happy to talk", "reply_contact": "harbour@example.org", "reply_slice": None,
             "from_hop": 1}
    r = client.post("/map/peer/introduction/reply", json=signed_envelope(key_b, "node-b", reply))
    assert r.status_code == 200 and r.json()["status"] == "accepted"

    mine = [i for i in client.get("/map/introductions", headers=auth(operator)).json()
            if i["correlation_id"] == intro["correlation_id"]][0]
    assert mine["status"] == "accepted" and mine["reply_contact"] == "harbour@example.org"


def test_a_reply_must_come_from_the_node_it_was_sent_to(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    key_c = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    add_peer(client, operator, "node-c", b64(bytes(key_c.verify_key)))
    capture_network(monkeypatch)
    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "hello", "offer": "work"}, headers=auth(operator)).json()
    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "reply_contact": "impostor@example.org", "reply_slice": None, "from_hop": 1}
    r = client.post("/map/peer/introduction/reply", json=signed_envelope(key_c, "node-c", reply))
    assert r.status_code == 422

    unknown = {"correlation_id": "nope", "status": "accepted", "reply_contact": "x", "from_hop": 1}
    assert client.post("/map/peer/introduction/reply",
                       json=signed_envelope(key_b, "node-b", unknown)).status_code == 404


def test_contact_reaches_the_asker_and_not_the_node_operator(client, node, operator, monkeypatch):
    """The reply is for the person who asked, not for everyone who can see the row."""
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    capture_network(monkeypatch)
    _, asker = did_login(client)
    create_profile(client, asker, "Asker")
    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "hello", "offer": "work"}, headers=auth(asker)).json()
    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "reply_contact": "harbour@example.org", "reply_slice": None, "from_hop": 1}
    client.post("/map/peer/introduction/reply", json=signed_envelope(key_b, "node-b", reply))

    theirs = [i for i in client.get("/map/introductions", headers=auth(asker)).json()
              if i["correlation_id"] == intro["correlation_id"]][0]
    assert theirs["reply_contact"] == "harbour@example.org"
    operators_view = [i for i in client.get("/map/introductions", headers=auth(operator)).json()
                      if i["correlation_id"] == intro["correlation_id"]][0]
    assert "reply_contact" not in operators_view


# --- several routes at once ----------------------------------------------------------------

def test_an_offer_takes_every_route_it_is_given(client, node, operator, monkeypatch):
    """One hop cannot stop an offer: it travels all the routes the asker knows."""
    add_peer(client, operator, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    add_peer(client, operator, "node-d", b64(bytes(SigningKey.generate().verify_key)))
    sent = capture_network(monkeypatch)
    r = client.post("/map/introductions", json={
        "paths": [["node-a", "node-b", "node-c"], ["node-a", "node-d", "node-c"]],
        **QUERY, "message": "hello", "offer": "refit work"}, headers=auth(operator)).json()

    assert r["status"] == "forwarded" and len(r["routes"]) == 2
    assert {s["peer"] for s in sent if s["path"] == "/map/peer/introduction"} == {"node-b", "node-d"}
    assert all(s["body"]["correlation_id"] == r["correlation_id"] for s in sent)  # one offer, two routes


def test_a_route_that_will_not_carry_is_a_missed_opportunity_not_a_fine(client, node, operator, monkeypatch):
    peer_b = add_peer(client, operator, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    add_peer(client, operator, "node-d", b64(bytes(SigningKey.generate().verify_key)))
    key_b = SigningKey.generate()

    def client_fn(peer, envelope, path="/map/peer/query"):
        if peer.node_id == "node-b":
            return None  # will not carry
        return {"status": "pending"}

    monkeypatch.setattr(forwarding, "PEER_CLIENT", client_fn)
    r = client.post("/map/introductions", json={
        "paths": [["node-a", "node-b", "node-c"], ["node-a", "node-d", "node-c"]],
        **QUERY, "message": "hello", "offer": "refit work"}, headers=auth(operator)).json()

    # the offer is still alive on the other route
    assert r["status"] == "forwarded"
    routes = {tuple(x["path"]): x for x in r["routes"]}
    assert routes[("node-a", "node-b", "node-c")]["status"] == "declined"
    assert routes[("node-a", "node-d", "node-c")]["status"] == "forwarded"

    after = [p for p in client.get("/map/peers", headers=auth(operator)).json() if p["node_id"] == "node-b"][0]
    assert after["missed_count"] == 1
    assert after["trust_weight"] == peer_b["trust_weight"]  # nothing deducted: only a chance not taken


def test_carrying_something_that_connects_builds_weight(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    peer = add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    capture_network(monkeypatch)
    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "hello", "offer": "refit work"},
                        headers=auth(operator)).json()
    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "reply_contact": "harbour@example.org", "reply_slice": None, "from_hop": 1}
    client.post("/map/peer/introduction/reply", json=signed_envelope(key_b, "node-b", reply))

    after = [p for p in client.get("/map/peers", headers=auth(operator)).json() if p["node_id"] == "node-b"][0]
    assert after["carried_count"] == 1 and after["connections_count"] == 1
    assert after["trust_weight"] == pytest.approx(peer["trust_weight"] + 0.05)  # connecting people is worth more


# --- the near side commits -------------------------------------------------------------------

def test_the_near_side_commits_after_the_far_side_accepts(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    sent = capture_network(monkeypatch)
    intro = client.post("/map/introductions", json={"paths": [["node-a", "node-b"]], **QUERY,
                                                    "message": "hello", "offer": "refit work in kind"},
                        headers=auth(operator)).json()
    assert intro["commit_status"] == "offered"
    # nothing to commit to until they say yes
    assert client.post(f"/map/introductions/{intro['id']}/commit", json={"contact": "us@example.org"},
                       headers=auth(operator)).status_code == 409

    reply = {"correlation_id": intro["correlation_id"], "status": "accepted",
             "reply_contact": "harbour@example.org", "reply_slice": None, "from_hop": 1}
    client.post("/map/peer/introduction/reply", json=signed_envelope(key_b, "node-b", reply))

    c = client.post(f"/map/introductions/{intro['id']}/commit",
                    json={"contact": "boatbuilders@example.org", "note": "we will start in January"},
                    headers=auth(operator)).json()
    assert c["commit_status"] == "committed"
    out = [s for s in sent if s["path"] == "/map/peer/introduction/commit"][-1]
    assert out["body"]["requester_contact"] == "boatbuilders@example.org"
    # and not twice
    assert client.post(f"/map/introductions/{intro['id']}/commit", json={"contact": "x@example.org"},
                       headers=auth(operator)).status_code == 409


def test_the_far_side_sees_who_it_is_dealing_with_only_after_they_commit(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", b64(bytes(key_b.verify_key)))
    _, holder = did_login(client)
    create_profile(client, holder, "Holder")
    item = client.post("/map/items", json=ITEM, headers=auth(holder)).json()
    capture_network(monkeypatch)

    body = {"correlation_id": "c9", "commitment": commitment(**QUERY), "offer": "refit work in kind",
            "path": ["node-b", "node-a"], "hop_index": 1, "message": "Boatbuilders need covered space."}
    client.post("/map/peer/introduction", json=signed_envelope(key_b, "node-b", body))
    mine = [i for i in client.get("/map/introductions", headers=auth(holder)).json()
            if i["correlation_id"] == "c9"][0]
    assert mine["offer"] == "refit work in kind"          # the holder decides knowing what is offered
    assert "requester_contact" not in mine                # and not yet who it is

    client.post(f"/map/introductions/{mine['id']}/decision",
                json={"accept": True, "reply_contact": "harbour@example.org", "share_items": [item["id"]]},
                headers=auth(holder))
    commit = {"correlation_id": "c9", "commit_status": "committed",
              "requester_contact": "boatbuilders@example.org", "note": "starting in January",
              "path": ["node-b", "node-a"]}
    r = client.post("/map/peer/introduction/commit", json=signed_envelope(key_b, "node-b", commit))
    assert r.status_code == 200 and r.json()["commit_status"] == "committed"

    after = [i for i in client.get("/map/introductions", headers=auth(holder)).json()
             if i["correlation_id"] == "c9"][0]
    assert after["requester_contact"] == "boatbuilders@example.org"
