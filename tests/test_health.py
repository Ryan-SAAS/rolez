from __future__ import annotations



async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


async def test_root_returns_metadata(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "rolez"
    assert "endpoints" in body
    assert body["endpoints"]["public"] == "/api/v1"
    assert body["endpoints"]["admin"] == "/api/admin"
    assert body["endpoints"]["cli"] == "/cli/rolez"
    # `/metrics` is NOT advertised — there's no metrics router yet, and the
    # root payload must not promise an endpoint that doesn't exist.
    assert "metrics" not in body["endpoints"]
