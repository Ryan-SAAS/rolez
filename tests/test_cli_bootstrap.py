from __future__ import annotations


async def test_cli_bootstrap_endpoint_serves_python_script(client):
    resp = await client.get("/cli/rolez")
    assert resp.status_code == 200
    body = resp.text
    assert body.startswith("#!/usr/bin/env python3")
    assert 'rolez — agent-side CLI' in body
    assert "argparse" in body
    # Content-Disposition should make `curl -O` write a file named "rolez":
    assert "rolez" in resp.headers.get("content-disposition", "")
