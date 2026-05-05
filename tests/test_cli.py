from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

CLI_PATH = Path(__file__).resolve().parent.parent / "cli" / "rolez"


def _load_cli():
    # Manual loader because the CLI file has no .py extension.
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("rolez_cli", str(CLI_PATH))
    spec = importlib.util.spec_from_loader("rolez_cli", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _mock_resp(status: int, body: dict | str = b"", headers: dict | None = None):
    if isinstance(body, dict):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        payload = body.encode("utf-8")
    else:
        payload = body
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = payload
    resp.headers = headers or {}
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setenv("ROLEZ_API_URL", "https://rolez.example")
    monkeypatch.setenv("ROLEZ_API_KEY", "test-token")
    return _load_cli()


def test_cli_list_renders_table(cli, capsys):
    body = {
        "total": 2,
        "items": [
            {"slug": "support-agent", "latest_version": "0.1.0", "description": "Support"},
            {"slug": "hr-agent", "latest_version": "0.2.0", "description": "HR"},
        ],
    }
    with patch("urllib.request.urlopen", return_value=_mock_resp(200, body)):
        rc = cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "support-agent" in out
    assert "0.1.0" in out
    assert "hr-agent" in out


def test_cli_list_json(cli, capsys):
    body = {"total": 1, "items": [{"slug": "x", "latest_version": "1.0.0"}]}
    with patch("urllib.request.urlopen", return_value=_mock_resp(200, body)):
        rc = cli.main(["list", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["slug"] == "x"


def test_cli_show(cli, capsys):
    body = {"slug": "support-agent", "latest_version": "0.1.0", "manifest": {"image": {"ref": "x"}}}
    with patch("urllib.request.urlopen", return_value=_mock_resp(200, body)):
        rc = cli.main(["show", "support-agent"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "support-agent" in out
    assert "image" in out


def test_cli_unauthorized_exits_with_auth_code(cli, capsys):
    import urllib.error
    err = urllib.error.HTTPError("u", 401, "u", {}, io.BytesIO(b'{"detail":"invalid api key"}'))
    with patch("urllib.request.urlopen", side_effect=err):
        rc = cli.main(["list"])
    assert rc != 0
    captured = capsys.readouterr()
    assert "unauthor" in captured.err.lower() or "401" in captured.err


def test_cli_missing_env_errors(monkeypatch, capsys):
    monkeypatch.delenv("ROLEZ_API_URL", raising=False)
    monkeypatch.delenv("ROLEZ_API_KEY", raising=False)
    cli = _load_cli()
    rc = cli.main(["list"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "ROLEZ_API_URL" in err or "api url" in err.lower()


def test_cli_search(cli, capsys):
    body = {"total": 2, "items": [
        {"slug": "support-agent", "latest_version": "0.1.0", "description": "Handles tickets"},
        {"slug": "support-pdf", "latest_version": "0.2.0", "description": "PDF flow"},
    ]}
    with patch("urllib.request.urlopen", return_value=_mock_resp(200, body)):
        rc = cli.main(["search", "support"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "support-agent" in out
    assert "support-pdf" in out


def test_cli_inspect_renders_summary(cli, capsys):
    """`inspect` must print image, skills, subagents, context_files names."""
    body = {
        "slug": "support-agent",
        "latest_version": "0.1.0",
        "manifest": {
            "image": {"ref": "saac/support-agent", "version": "1.4.0"},
            "skills": [{"name": "pdf-generator", "version": "1.2.3"}],
            "subagents": [{"name": "code-reviewer", "version": "0.5.0"}],
            "context_files": [{"name": "CLAUDE.md", "content": "..."}],
        },
    }
    with patch("urllib.request.urlopen", return_value=_mock_resp(200, body)):
        rc = cli.main(["inspect", "support-agent"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "saac/support-agent@1.4.0" in out
    assert "pdf-generator@1.2.3" in out
    assert "code-reviewer@0.5.0" in out
    assert "CLAUDE.md" in out


def test_cli_inspect_falls_back_to_raw_when_manifest_missing(cli, capsys):
    body = {"slug": "x", "latest_version": "1.0.0"}  # no manifest field
    with patch("urllib.request.urlopen", return_value=_mock_resp(200, body)):
        rc = cli.main(["inspect", "x"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "x" in out


def test_cli_no_audit_command(cli):
    """The audit command was removed because the endpoint never existed.
    Confirm argparse rejects it so we don't accidentally re-introduce a
    broken command."""
    rc = cli.main(["audit"])
    assert rc != 0
