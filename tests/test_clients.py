from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.agentz import AgentzClient, AgentzNotFound
from app.clients.skillz import SkillzClient, SkillzNotFound
from app.clients.techsaac import TechsaacClient, TechsaacError


@respx.mock
async def test_skillz_get_skill_returns_latest_version():
    respx.get("https://skillz.example/api/v1/skills/pdf-generator").mock(
        return_value=httpx.Response(200, json={
            "name": "pdf-generator",
            "latest_version": "1.2.3",
            "versions": [{"version": "1.2.3"}, {"version": "1.2.2"}],
        })
    )
    c = SkillzClient(base_url="https://skillz.example", token="t")
    out = await c.get_skill("pdf-generator")
    assert out["latest_version"] == "1.2.3"


@respx.mock
async def test_skillz_404_raises_not_found():
    respx.get("https://skillz.example/api/v1/skills/missing").mock(
        return_value=httpx.Response(404, json={"detail": "skill not found"})
    )
    c = SkillzClient(base_url="https://skillz.example", token="t")
    with pytest.raises(SkillzNotFound):
        await c.get_skill("missing")


@respx.mock
async def test_skillz_sends_bearer_header():
    route = respx.get("https://skillz.example/api/v1/skills/x").mock(
        return_value=httpx.Response(200, json={"name": "x", "latest_version": "0.1.0", "versions": []})
    )
    c = SkillzClient(base_url="https://skillz.example", token="my-skillz-token")
    await c.get_skill("x")
    assert route.calls[0].request.headers["authorization"] == "Bearer my-skillz-token"


@respx.mock
async def test_agentz_get_agent_returns_latest_version():
    respx.get("https://agentz.example/api/v1/agents/code-reviewer").mock(
        return_value=httpx.Response(200, json={
            "name": "code-reviewer", "latest_version": "0.5.0", "versions": [{"version": "0.5.0"}],
        })
    )
    c = AgentzClient(base_url="https://agentz.example", token="t")
    out = await c.get_agent("code-reviewer")
    assert out["latest_version"] == "0.5.0"


@respx.mock
async def test_agentz_404_raises_not_found():
    respx.get("https://agentz.example/api/v1/agents/nope").mock(
        return_value=httpx.Response(404, json={"detail": "agent not found"})
    )
    c = AgentzClient(base_url="https://agentz.example", token="t")
    with pytest.raises(AgentzNotFound):
        await c.get_agent("nope")


@respx.mock
async def test_techsaac_call_tool_forwards_apikey_and_returns_result():
    route = respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": 1,
            "result": {"agent_id": "agent-uuid", "status": "starting"},
        })
    )
    c = TechsaacClient(base_url="https://techsaac.example/api/mcp")
    out = await c.call_tool("create_agent", {"name": "support-eu"}, caller_token="caller-token")
    assert out["agent_id"] == "agent-uuid"
    assert route.calls[0].request.headers["authorization"] == "ApiKey caller-token"
    body = route.calls[0].request.read()
    assert b"create_agent" in body
    assert b"support-eu" in body


@respx.mock
async def test_techsaac_call_tool_raises_on_jsonrpc_error():
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32603, "message": "boom"},
        })
    )
    c = TechsaacClient(base_url="https://techsaac.example/api/mcp")
    with pytest.raises(TechsaacError) as ei:
        await c.call_tool("create_agent", {}, caller_token="caller-token")
    assert "boom" in str(ei.value)


@respx.mock
async def test_techsaac_propagates_http_error_status():
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(401, json={"error": "UNAUTHORIZED"})
    )
    c = TechsaacClient(base_url="https://techsaac.example/api/mcp")
    with pytest.raises(TechsaacError) as ei:
        await c.call_tool("create_agent", {}, caller_token="bad")
    assert ei.value.status_code == 401
