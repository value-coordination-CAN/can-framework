from app.models.network_edge import NetworkEdge
from app.services.linkedin_importer import hash_external
from app.services.network_graph import DECAY, find_paths
from conftest import auth, create_profile, did_login

CSV = (
    "First Name,Last Name,URL,Email Address\n"
    "Jane,Doe,https://www.linkedin.com/in/janedoe,jane@example.org\n"
    "John,Roe,https://www.linkedin.com/in/johnroe,\n"
    ",,,\n"
)


def test_linkedin_import_stores_keyed_hash_only(client, db_session_factory):
    _, alice = did_login(client)
    alice_id = create_profile(client, alice, "Alice")
    r = client.post(
        "/integrations/linkedin/import",
        files={"file": ("Connections.csv", CSV, "text/csv")},
        headers=auth(alice),
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2 and r.json()["skipped"] == 1

    db = db_session_factory()
    edges = db.query(NetworkEdge).filter(NetworkEdge.source_user_id == alice_id).all()
    db.close()
    assert all(e.display_name is None for e in edges)
    import hashlib
    unsalted = "li:" + hashlib.sha256(b"https://www.linkedin.com/in/janedoe").hexdigest()
    ids = {e.target_external_id for e in edges}
    assert unsalted not in ids
    assert hash_external("https://www.linkedin.com/in/janedoe") in ids

    r = client.delete("/integrations/linkedin/import", headers=auth(alice))
    assert r.json()["deleted"] == 2


def _edge(db, s, t, w):
    db.add(NetworkEdge(source_user_id=s, target_user_id=t, weight=w, source_system="manual"))


def test_find_paths_returns_alternatives_and_decays_once(db_session_factory):
    db = db_session_factory()
    # A -> B -> D and A -> C -> D (two equal-length routes), plus a cycle B -> A
    _edge(db, "A", "B", 1.0)
    _edge(db, "A", "C", 0.5)
    _edge(db, "B", "D", 1.0)
    _edge(db, "C", "D", 1.0)
    _edge(db, "B", "A", 1.0)
    db.commit()

    res = find_paths(db, "A", "D", max_depth=4, top_n=5)
    assert res["found"] == 2
    best, second = res["paths"]
    assert best["distance"] == 2
    assert best["confidence"] == DECAY  # 1.0 * 1.0 * DECAY^(2-1)
    assert second["confidence"] == 0.5 * DECAY
    db.close()
