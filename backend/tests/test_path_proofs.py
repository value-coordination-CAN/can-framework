"""Path proofs: a degree cannot be shortened, and a match cannot be claimed for someone else."""
import base64
import json

import pytest
from nacl.signing import SigningKey

from app.core.config import settings
from app.value import forwarding
from app.value.commitments import commitment
from app.value.engine import load_value_config
from app.value.proofs import proof_hash
from conftest import auth, create_profile, did_login, token_with_roles

QUERY = {"item_type": "capacity", "item_class": "covered_workshop", "region": "GCC-E", "period": "2027-Q1"}
ITEM = {"item_type": "capacity", "item_class": "covered_workshop", "title": "Two bays",
        "region": "GCC-E", "available_from": "2027-01-15", "discoverable": True}


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def attest(key: SigningKey, node_id: str, payload: dict) -> dict:
    return {"node_id": node_id, "public_key": b64(bytes(key.verify_key)),
            "payload": payload, "value": b64(key.sign(canon(payload)).signature)}


def match_att(key, node_id, query_id, target):
    return attest(key, node_id, {"kind": "match", "query_id": query_id, "commitment": target,
                                 "node_id": node_id})


def hop_att(key, node_id, query_id, target, from_node, inner):
    return attest(key, node_id, {"kind": "hop", "query_id": query_id, "commitment": target,
                                 "node_id": node_id, "from_node": from_node,
                                 "inner_hash": proof_hash(inner)})


@pytest.fixture()
def node(monkeypatch):
    key = SigningKey.generate()
    monkeypatch.setattr(settings, "NODE_ID", "node-a")
    monkeypatch.setattr(settings, "NODE_SIGNING_KEY", b64(bytes(key)))
    monkeypatch.setattr(load_value_config(), "discovery",
                        {"k_anonymity": 1, "epoch_days": 7, "max_queries_per_hour": 200,
                         "max_degree_default": 3, "max_degree_limit": 6, "hop_decay": 0.6,
                         "peer_timeout_seconds": 1, "peer_max_queries_per_hour": 240})
    return key


@pytest.fixture()
def operator(client, db_session_factory):
    did, _ = did_login(client)
    token = token_with_roles(db_session_factory, did, ["can_user", "can_admin"])
    create_profile(client, token, "Operator")
    return token


def add_peer(client, admin, node_id, key, weight=0.8):
    r = client.post("/map/peers", json={"node_id": node_id, "public_key": b64(bytes(key.verify_key)),
                                        "base_url": "http://peer.invalid", "trust_weight": weight},
                    headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()


def network(monkeypatch, make_results):
    """A peer that answers with whatever `make_results(query_id, commitment)` builds."""
    def client_fn(peer, envelope, path="/map/peer/query"):
        body = envelope["body"]
        return {"node_id": peer.node_id,
                "results": make_results(body.get("query_id", ""), body["commitment"], body["path"])}

    monkeypatch.setattr(forwarding, "PEER_CLIENT", client_fn)


def ask(client, token, **extra):
    return client.post("/map/query/federated", json={**QUERY, **extra}, headers=auth(token)).json()


# --- honest answers -----------------------------------------------------------------------

def test_a_local_match_is_proven_by_this_node(client, node, operator):
    _, holder = did_login(client)
    create_profile(client, holder, "Holder")
    client.post("/map/items", json=ITEM, headers=auth(holder))
    r = ask(client, operator)
    assert r["found"] == 1
    result = r["results"][0]
    assert result["proven"] is True and result["node_id"] == "node-a"
    assert result["proof"]["match"]["payload"]["query_id"] == r["query_id"]


def test_a_neighbour_that_signs_its_match_is_proven(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-b", "path": path + ["node-b"], "degree": 1, "confidence": 1.0, "match": True,
         "proof": {"match": match_att(key_b, "node-b", qid, target), "hops": []}}])
    r = ask(client, operator)
    assert r["results"][0]["proven"] is True and r["results"][0]["degree"] == 1


def test_two_hops_need_the_relay_signature_as_well(client, node, operator, monkeypatch):
    key_b, key_c = SigningKey.generate(), SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)

    def results(qid, target, path):
        match = match_att(key_c, "node-c", qid, target)
        inner = {"match": match, "hops": []}
        hop = hop_att(key_b, "node-b", qid, target, "node-c", inner)
        return [{"node_id": "node-c", "path": path + ["node-b", "node-c"], "degree": 2,
                 "confidence": 0.6, "match": True,
                 "proof": {"match": match, "hops": [hop]}}]

    network(monkeypatch, results)
    r = ask(client, operator)
    assert r["results"][0]["proven"] is True and r["results"][0]["path"][-1] == "node-c"


# --- dishonest ones -----------------------------------------------------------------------

def test_a_node_cannot_claim_a_match_it_does_not_hold(client, node, operator, monkeypatch):
    """node-b says the match is at node-c, but signs the attestation itself."""
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-c", "path": path + ["node-b", "node-c"], "degree": 2, "confidence": 0.6,
         "match": True,
         "proof": {"match": match_att(key_b, "node-b", qid, target),   # wrong signer
                   "hops": [hop_att(key_b, "node-b", qid, target, "node-c",
                                    {"match": match_att(key_b, "node-b", qid, target), "hops": []})]}}])
    r = ask(client, operator)
    assert r["results"][0]["proven"] is False
    assert any("path ends at" in p for p in r["results"][0]["proof_problems"])
    assert ask(client, operator, proven_only=True)["found"] == 0


def test_a_degree_cannot_be_shortened(client, node, operator, monkeypatch):
    """node-b passes on a match that is really two hops away, but claims it is one."""
    key_b, key_c = SigningKey.generate(), SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-c", "path": path + ["node-c"], "degree": 1, "confidence": 1.0, "match": True,
         "proof": {"match": match_att(key_c, "node-c", qid, target),
                   "hops": [hop_att(key_b, "node-b", qid, target, "node-c",
                                    {"match": match_att(key_c, "node-c", qid, target), "hops": []})]}}])
    r = ask(client, operator)
    assert r["results"][0]["proven"] is False
    assert any("relay signature" in p for p in r["results"][0]["proof_problems"])


def test_a_forged_signature_is_refused(client, node, operator, monkeypatch):
    key_b, impostor = SigningKey.generate(), SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-b", "path": path + ["node-b"], "degree": 1, "confidence": 1.0, "match": True,
         "proof": {"match": match_att(impostor, "node-b", qid, target), "hops": []}}])  # not node-b's key
    r = ask(client, operator)
    assert r["results"][0]["proven"] is False
    assert any("key this node does not hold" in p for p in r["results"][0]["proof_problems"])


def test_a_proof_from_another_question_cannot_be_replayed(client, node, operator, monkeypatch):
    key_b = SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-b", "path": path + ["node-b"], "degree": 1, "confidence": 1.0, "match": True,
         "proof": {"match": match_att(key_b, "node-b", "an-older-query", target), "hops": []}}])
    r = ask(client, operator)
    assert r["results"][0]["proven"] is False
    assert any("different question" in p for p in r["results"][0]["proof_problems"])


def test_a_broken_chain_is_refused(client, node, operator, monkeypatch):
    """node-b signs a hop whose inner hash does not match what it hands over."""
    key_b, key_c = SigningKey.generate(), SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-c", "path": path + ["node-b", "node-c"], "degree": 2, "confidence": 0.6,
         "match": True,
         "proof": {"match": match_att(key_c, "node-c", qid, target),
                   "hops": [hop_att(key_b, "node-b", qid, target, "node-c", {"match": None, "hops": []})]}}])
    r = ask(client, operator)
    assert r["results"][0]["proven"] is False
    assert any("chain is broken" in p for p in r["results"][0]["proof_problems"])


def test_an_answer_with_no_proof_is_carried_but_marked(client, node, operator, monkeypatch):
    """A node without a signing key cannot prove anything. Its answers are not silently dropped."""
    add_peer(client, operator, "node-b", SigningKey.generate())
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-b", "path": path + ["node-b"], "degree": 1, "confidence": 1.0, "match": True}])
    r = ask(client, operator)
    assert r["found"] == 1 and r["results"][0]["proven"] is False
    assert "does not sign" in r["results"][0]["proof_problems"][0]
    assert ask(client, operator, proven_only=True)["found"] == 0


def test_a_relay_signs_what_it_passes_on(client, node, operator, monkeypatch):
    """Inbound: this node relays an answer and adds its own link to the chain."""
    key_b, key_c = SigningKey.generate(), SigningKey.generate()
    add_peer(client, operator, "node-b", key_b)
    add_peer(client, operator, "node-c", key_c)
    network(monkeypatch, lambda qid, target, path: [
        {"node_id": "node-c", "path": path + ["node-c"], "degree": 1, "confidence": 1.0, "match": True,
         "proof": {"match": match_att(key_c, "node-c", qid, target), "hops": []}}])

    body = {"commitment": commitment(**QUERY), "ttl": 2, "path": ["node-b"], "query_id": "q-1"}
    envelope = {"body": body, "from_node": "node-b",
                "signature": b64(key_b.sign(forwarding.canonical(body)).signature)}
    r = client.post("/map/peer/query", json=envelope).json()
    relayed = [x for x in r["results"] if x["node_id"] == "node-c"][0]
    hop = relayed["proof"]["hops"][-1]
    assert hop["node_id"] == "node-a" and hop["payload"]["from_node"] == "node-c"
    assert hop["payload"]["inner_hash"] == proof_hash({"match": relayed["proof"]["match"], "hops": []})
