"""WP-012 steps 3 and 4: peering, and a query that travels hops and comes back as a path."""
import base64

import pytest
from nacl.signing import SigningKey

from app.core.config import settings
from app.value import forwarding
from app.value.commitments import commitment
from app.value.engine import load_value_config
from conftest import auth, create_profile, did_login, token_with_roles

QUERY = {"item_type": "capacity", "item_class": "covered_workshop", "region": "GCC-E", "period": "2027-Q1"}
TARGET = None  # computed per test, after the epoch salt is known


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture()
def node_a(monkeypatch):
    """This node: node-a, with a signing key so it can forward."""
    key = SigningKey.generate()
    monkeypatch.setattr(settings, "NODE_ID", "node-a")
    monkeypatch.setattr(settings, "NODE_SIGNING_KEY", b64(bytes(key)))
    monkeypatch.setattr(load_value_config(), "discovery",
                        {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 120,
                         "max_degree_default": 3, "max_degree_limit": 6, "hop_decay": 0.6,
                         "peer_timeout_seconds": 1, "peer_max_queries_per_hour": 240})
    return key


@pytest.fixture()
def admin(client, db_session_factory):
    did, _ = did_login(client)
    token = token_with_roles(db_session_factory, did, ["can_user", "can_admin"])
    create_profile(client, token, "Operator")
    return token


def add_peer(client, admin_token, node_id, public_key, weight=0.5, base_url="http://peer.invalid"):
    return client.post("/map/peers", json={"node_id": node_id, "public_key": public_key,
                                           "base_url": base_url, "trust_weight": weight},
                       headers=auth(admin_token))


def fake_network(monkeypatch, topology):
    """Stand in for the peers' HTTP endpoints.

    `topology` maps a peer node id to the results it returns, as that node would:
    its own local matches sealed to confidence 1.0, plus anything it got from further away.
    Every call is checked for a valid signature from node-a, exactly as a real peer would.
    """
    calls = []

    def client(peer, envelope):
        forwarding.canonical(envelope["body"])  # shape check
        assert envelope["from_node"] == settings.NODE_ID
        # a real peer verifies the signature; do the same here
        from nacl.signing import VerifyKey
        VerifyKey(forwarding._unb64(b64(bytes(SigningKey(forwarding._unb64(settings.NODE_SIGNING_KEY)).verify_key)))
                  ).verify(forwarding.canonical(envelope["body"]),
                           forwarding._unb64(envelope["signature"]))
        calls.append({"peer": peer.node_id, "body": envelope["body"]})
        return topology.get(peer.node_id, {"node_id": peer.node_id, "results": []})

    monkeypatch.setattr(forwarding, "PEER_CLIENT", client)
    return calls


# --- peering ---------------------------------------------------------------------------

def test_peering_is_deliberate_and_only_operators_do_it(client, node_a, admin):
    other = SigningKey.generate()
    r = add_peer(client, admin, "node-b", b64(bytes(other.verify_key)), weight=0.7)
    assert r.status_code == 201 and r.json()["trust_weight"] == 0.7

    _, ordinary = did_login(client)
    create_profile(client, ordinary, "Ordinary")
    assert add_peer(client, ordinary, "node-c", b64(bytes(SigningKey.generate().verify_key))).status_code == 403
    assert client.get("/map/peers", headers=auth(ordinary)).status_code == 403

    assert add_peer(client, admin, "node-b", b64(bytes(other.verify_key))).status_code == 409
    assert add_peer(client, admin, "node-a", b64(bytes(other.verify_key))).status_code == 422  # not itself


def test_a_peer_can_be_suspended_and_removed(client, node_a, admin):
    peer = add_peer(client, admin, "node-b", b64(bytes(SigningKey.generate().verify_key))).json()
    assert client.patch(f"/map/peers/{peer['id']}", json={"status": "suspended"},
                        headers=auth(admin)).json()["status"] == "suspended"
    assert client.delete(f"/map/peers/{peer['id']}", headers=auth(admin)).status_code == 200
    assert client.get("/map/peers", headers=auth(admin)).json() == []


# --- forwarding -------------------------------------------------------------------------

def test_a_query_travels_and_comes_back_as_a_path(client, node_a, admin, monkeypatch):
    target = commitment(**QUERY)
    add_peer(client, admin, "node-b", b64(bytes(SigningKey.generate().verify_key)), weight=0.8)
    calls = fake_network(monkeypatch, {
        "node-b": {"node_id": "node-b", "results": [
            {"node_id": "node-b", "path": ["node-a", "node-b"], "degree": 1, "confidence": 1.0, "match": True},
            {"node_id": "node-c", "path": ["node-a", "node-b", "node-c"], "degree": 2,
             "confidence": round(0.5 * 1.0 * 0.6, 6), "match": True},  # node-b's own hop weight to node-c
        ]},
    })

    r = client.post("/map/query/federated", json={**QUERY, "max_degree": 3}, headers=auth(admin)).json()
    assert r["found"] == 2
    near, far = r["results"]
    assert near["node_id"] == "node-b" and near["degree"] == 1
    assert near["confidence"] == pytest.approx(0.8 * 0.6)          # one hop, weight 0.8, decayed once
    assert far["node_id"] == "node-c" and far["degree"] == 2
    assert far["confidence"] == pytest.approx(0.8 * 0.3 * 0.6)     # compounded through node-b
    # the query that went out carried the commitment, a reduced ttl, the path so far and
    # the query id that every proof is bound to
    assert calls[0]["body"] == {"commitment": target, "ttl": 2, "path": ["node-a"],
                                "query_id": r["query_id"]}
    # a result carries a path, a confidence and whether its proof stands up; nothing about
    # what was found. These answers are unsigned, so they arrive unproven.
    assert set(near) <= {"node_id", "path", "degree", "confidence", "match", "proven", "proof_problems"}
    assert near["proven"] is False


def test_results_below_the_confidence_floor_are_dropped(client, node_a, admin, monkeypatch):
    add_peer(client, admin, "node-b", b64(bytes(SigningKey.generate().verify_key)), weight=0.2)
    fake_network(monkeypatch, {"node-b": {"node_id": "node-b", "results": [
        {"node_id": "node-b", "path": ["node-a", "node-b"], "degree": 1, "confidence": 1.0, "match": True}]}})
    r = client.post("/map/query/federated", json={**QUERY, "min_confidence": 0.5}, headers=auth(admin)).json()
    assert r["found"] == 0  # 0.2 x 0.6 = 0.12, below the floor


def test_hops_are_bounded_by_this_nodes_limit(client, node_a, admin, monkeypatch):
    add_peer(client, admin, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    calls = fake_network(monkeypatch, {})
    client.post("/map/query/federated", json={**QUERY, "max_degree": 6}, headers=auth(admin))
    assert calls[0]["body"]["ttl"] == 5
    calls.clear()
    client.post("/map/query/federated", json={**QUERY, "max_degree": 0}, headers=auth(admin))
    assert calls == []  # nothing forwarded at degree zero


def test_a_node_does_not_forward_to_somewhere_already_on_the_path(client, node_a, admin, monkeypatch):
    add_peer(client, admin, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    key_c = SigningKey.generate()
    add_peer(client, admin, "node-c", b64(bytes(key_c.verify_key)))
    calls = fake_network(monkeypatch, {})

    # node-c asks us, and its own id is already in the path: we must not call it back
    envelope = {"body": {"commitment": commitment(**QUERY), "ttl": 2, "path": ["node-c"]},
                "from_node": "node-c",
                "signature": b64(key_c.sign(forwarding.canonical(
                    {"commitment": commitment(**QUERY), "ttl": 2, "path": ["node-c"]})).signature)}
    r = client.post("/map/peer/query", json=envelope)
    assert r.status_code == 200
    assert [c["peer"] for c in calls] == ["node-b"]


# --- inbound peer requests ---------------------------------------------------------------

def test_inbound_queries_must_be_signed_by_a_known_peer(client, node_a, admin):
    body = {"commitment": commitment(**QUERY), "ttl": 0, "path": []}
    stranger = SigningKey.generate()
    envelope = {"body": body, "from_node": "node-x",
                "signature": b64(stranger.sign(forwarding.canonical(body)).signature)}
    assert client.post("/map/peer/query", json=envelope).status_code == 403  # not a peer

    add_peer(client, admin, "node-x", b64(bytes(SigningKey.generate().verify_key)))  # wrong key on file
    r = client.post("/map/peer/query", json=envelope)
    assert r.status_code == 403 and "signature" in r.json()["detail"]


def test_a_suspended_peer_is_not_answered(client, node_a, admin):
    key_b = SigningKey.generate()
    peer = add_peer(client, admin, "node-b", b64(bytes(key_b.verify_key))).json()
    client.patch(f"/map/peers/{peer['id']}", json={"status": "suspended"}, headers=auth(admin))
    body = {"commitment": commitment(**QUERY), "ttl": 0, "path": []}
    envelope = {"body": body, "from_node": "node-b",
                "signature": b64(key_b.sign(forwarding.canonical(body)).signature)}
    r = client.post("/map/peer/query", json=envelope)
    assert r.status_code == 403 and "suspended" in r.json()["detail"]


def test_an_inbound_query_is_answered_from_this_nodes_own_items(client, node_a, admin):
    key_b = SigningKey.generate()
    add_peer(client, admin, "node-b", b64(bytes(key_b.verify_key)))
    _, holder = did_login(client)
    create_profile(client, holder, "LocalHolder")
    client.post("/map/items", json={"item_type": "capacity", "item_class": "covered_workshop",
                                    "title": "Two bays", "region": "GCC-E", "available_from": "2027-01-15",
                                    "discoverable": True}, headers=auth(holder))

    body = {"commitment": commitment(**QUERY), "ttl": 0, "path": ["node-b"]}
    envelope = {"body": body, "from_node": "node-b",
                "signature": b64(key_b.sign(forwarding.canonical(body)).signature)}
    r = client.post("/map/peer/query", json=envelope).json()
    assert r["results"][0]["node_id"] == "node-a" and r["results"][0]["confidence"] == 1.0
    assert r["results"][0]["path"] == ["node-b", "node-a"]
    assert "Two bays" not in str(r)


def test_a_node_does_not_answer_twice_in_one_path(client, node_a, admin):
    key_b = SigningKey.generate()
    add_peer(client, admin, "node-b", b64(bytes(key_b.verify_key)))
    body = {"commitment": commitment(**QUERY), "ttl": 2, "path": ["node-a", "node-b"]}
    envelope = {"body": body, "from_node": "node-b",
                "signature": b64(key_b.sign(forwarding.canonical(body)).signature)}
    r = client.post("/map/peer/query", json=envelope).json()
    assert r["results"] == [] and "already visited" in r["note"]


# --- the local record of what was asked ----------------------------------------------------

def test_the_node_keeps_a_log_of_what_it_was_asked(client, node_a, admin, monkeypatch):
    add_peer(client, admin, "node-b", b64(bytes(SigningKey.generate().verify_key)))
    fake_network(monkeypatch, {})
    client.post("/map/query/federated", json=QUERY, headers=auth(admin))
    log = client.get("/map/queries", headers=auth(admin)).json()
    assert log and log[0]["direction"] == "local" and log[0]["path"] == []
    # the log records a fingerprint, not the commitment itself, and never the contents
    assert len(log[0]["commitment"]) == 12
    _, ordinary = did_login(client)
    create_profile(client, ordinary, "Nosy")
    assert client.get("/map/queries", headers=auth(ordinary)).status_code == 403
