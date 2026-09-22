def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["message"] == "ok"


def test_optional_routers_are_mounted(client):
    paths = {r.path for r in client.app.routes}
    assert "/integrations/linkedin/import" in paths
    assert "/network/path" in paths
