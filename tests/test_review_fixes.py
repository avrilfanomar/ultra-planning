from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.fixtures import valid_bundle
from ultra_plan.agents import claude as claude_agent
from ultra_plan.agents import opencode as opencode_agent
from ultra_plan.review import server as review_server
from ultra_plan.validate import validate_bundle

# --- Fix 1: stdin-based prompt -----------------------------------------------

def test_claude_pipes_prompt_via_stdin(monkeypatch):
    captured: dict = {}

    def fake_run(cmd, *, input=None, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = input
        result = MagicMock()
        result.stdout = json.dumps(
            {"result": "===BUNDLE-BEGIN===\n{\"ok\":1}\n===BUNDLE-END==="}
        )
        return result

    monkeypatch.setattr(claude_agent.subprocess, "run", fake_run)
    out = claude_agent.run("--evil prompt", allowed_tools=["Read"])
    assert out == {"ok": 1}
    # Prompt is NOT in argv; it went via stdin.
    assert "--evil prompt" not in captured["cmd"]
    assert captured["input"] == "--evil prompt"


def test_opencode_pipes_prompt_via_stdin(monkeypatch):
    captured: dict = {}

    def fake_run(cmd, *, input=None, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = input
        result = MagicMock()
        result.stdout = "===BUNDLE-BEGIN===\n{\"ok\":2}\n===BUNDLE-END==="
        return result

    monkeypatch.setattr(opencode_agent.subprocess, "run", fake_run)
    out = opencode_agent.run("--leading-dash", allowed_tools=[])
    assert out == {"ok": 2}
    assert "--leading-dash" not in captured["cmd"]
    assert captured["input"] == "--leading-dash"


# --- Fix 4: robust envelope parser -------------------------------------------

def test_claude_unknown_envelope_raises_descriptive_error(monkeypatch):
    def fake_run(cmd, *, input=None, **kwargs):
        result = MagicMock()
        result.stdout = json.dumps({"weird_key": 1, "another": "x"})
        return result

    monkeypatch.setattr(claude_agent.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        claude_agent.run("hi", allowed_tools=[])
    msg = str(exc.value)
    assert "weird_key" in msg
    assert "another" in msg


# --- Fix 5: skills schema accepts `auth` -------------------------------------

def test_skill_with_auth_validates():
    bundle = valid_bundle()
    bundle["skills"][0]["auth"] = "GITHUB_TOKEN env"
    validate_bundle(bundle)  # must not raise


# --- Fix 7: friendly errors for missing binary / nonzero exit ----------------

def test_claude_missing_binary_friendly_error(monkeypatch):
    def fake_run(*a, **kw):
        raise FileNotFoundError(2, "No such file", "claude")

    monkeypatch.setattr(claude_agent.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="claude CLI not found on PATH"):
        claude_agent.run("hi", allowed_tools=[])


def test_opencode_missing_binary_friendly_error(monkeypatch):
    def fake_run(*a, **kw):
        raise FileNotFoundError(2, "No such file", "opencode")

    monkeypatch.setattr(opencode_agent.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="opencode CLI not found on PATH"):
        opencode_agent.run("hi", allowed_tools=[])


def test_claude_calledprocesserror_includes_stderr_tail(monkeypatch):
    def fake_run(*a, **kw):
        raise subprocess.CalledProcessError(
            returncode=2, cmd=["claude"], output="", stderr="boom-tail"
        )

    monkeypatch.setattr(claude_agent.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="boom-tail"):
        claude_agent.run("hi", allowed_tools=[])


# --- Fixes 2, 3, 6: review server --------------------------------------------
#
# We exercise the handler logic directly by constructing a minimal handler
# instance via __new__ so we don't have to spin up sockets for these checks.

class _FakeServer:
    server_address = ("127.0.0.1", 7777)


def _make_handler(out_dir: Path, headers: dict[str, str] | None = None):
    h = review_server._Handler.__new__(review_server._Handler)
    h.out_dir = out_dir
    h.server = _FakeServer()
    sent: list[tuple[int, bytes]] = []

    def _send(status: int, body: bytes, ctype: str = "application/json") -> None:
        sent.append((status, body))

    h._send = _send  # type: ignore[assignment]
    h.headers = headers or {}
    return h, sent


def test_read_body_rejects_oversize_content_length(tmp_path):
    h, _ = _make_handler(tmp_path, {"Content-Length": str(review_server.MAX_BODY + 1)})
    assert h._read_body() is None


def test_check_origin_allows_missing_origin(tmp_path):
    h, _ = _make_handler(tmp_path, {})
    assert h._check_origin() is True


def test_check_origin_allows_loopback(tmp_path):
    h, _ = _make_handler(tmp_path, {"Origin": "http://127.0.0.1:7777"})
    assert h._check_origin() is True
    h.headers = {"Origin": "http://localhost:7777"}
    assert h._check_origin() is True


def test_check_origin_rejects_other(tmp_path):
    h, _ = _make_handler(tmp_path, {"Origin": "http://evil.example.com"})
    assert h._check_origin() is False


def test_put_responds_413_when_body_too_large(tmp_path):
    h, sent = _make_handler(tmp_path, {"Content-Length": str(review_server.MAX_BODY + 1)})
    h.path = "/bundle"
    h.do_PUT()
    assert sent and sent[0][0] == 413


def test_put_responds_403_when_origin_bad(tmp_path):
    h, sent = _make_handler(
        tmp_path, {"Content-Length": "0", "Origin": "http://evil.example.com"}
    )
    h.path = "/bundle"
    h.do_PUT()
    assert sent and sent[0][0] == 403


def test_put_responds_403_when_token_missing(tmp_path):
    h, sent = _make_handler(tmp_path, {"Content-Length": "0"})
    # Bind a token onto the instance to enable token enforcement.
    h.token = "secret-token-xyz"
    h.path = "/bundle"
    h.do_PUT()
    assert sent and sent[0][0] == 403


def test_put_responds_403_when_token_wrong(tmp_path):
    h, sent = _make_handler(
        tmp_path,
        {"Content-Length": "0", "X-Ultra-Plan-Token": "nope"},
    )
    h.token = "secret-token-xyz"
    h.path = "/bundle"
    h.do_PUT()
    assert sent and sent[0][0] == 403


def test_post_responds_403_when_token_missing(tmp_path):
    h, sent = _make_handler(tmp_path, {"Content-Length": "0"})
    h.token = "secret-token-xyz"
    h.path = "/confirm"
    h.do_POST()
    assert sent and sent[0][0] == 403


def test_put_succeeds_with_valid_token_header(tmp_path, monkeypatch):
    # Bypass schema validation (jsonschema registry kwarg issue pre-existing).
    monkeypatch.setattr(review_server, "_validate_or_error", lambda b: None)
    payload = json.dumps({"task": "x"}).encode()

    class _BodyReader:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self, n: int) -> bytes:
            d, self._data = self._data[:n], self._data[n:]
            return d

    h, sent = _make_handler(
        tmp_path,
        {
            "Content-Length": str(len(payload)),
            "X-Ultra-Plan-Token": "secret-token-xyz",
        },
    )
    h.token = "secret-token-xyz"
    h.rfile = _BodyReader(payload)
    h.path = "/bundle"
    h.do_PUT()
    assert sent and sent[0][0] == 200
    # Atomic helper must not leave .tmp files around on the happy path.
    assert (tmp_path / "bundle.json").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_put_succeeds_with_valid_token_query_param(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "_validate_or_error", lambda b: None)
    payload = json.dumps({"task": "x"}).encode()

    class _BodyReader:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self, n: int) -> bytes:
            d, self._data = self._data[:n], self._data[n:]
            return d

    h, sent = _make_handler(tmp_path, {"Content-Length": str(len(payload))})
    h.token = "secret-token-xyz"
    h.rfile = _BodyReader(payload)
    h.path = "/bundle?token=secret-token-xyz"
    h.do_PUT()
    assert sent and sent[0][0] == 200


def test_atomic_write_no_tmp_files_left(tmp_path):
    review_server._atomic_write_text(tmp_path / "out.json", '{"a":1}')
    assert (tmp_path / "out.json").read_text() == '{"a":1}'
    assert not list(tmp_path.glob("*.tmp"))


def test_write_derived_artifacts_leaves_no_tmp(tmp_path):
    bundle = valid_bundle()
    review_server.write_derived_artifacts(tmp_path, bundle)
    assert (tmp_path / "bundle.json").exists()
    assert (tmp_path / "skills.json").exists()
    assert (tmp_path / "plan.md").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_serve_falls_back_to_ephemeral_port_when_busy(tmp_path, monkeypatch):
    import socket

    # Occupy a port on 127.0.0.1, then ask serve() to bind to it.
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy_port = blocker.getsockname()[1]

    # Patch serve_forever to return immediately so serve() doesn't block.
    started: dict = {}

    real_bind = review_server._bind_server

    def fake_bind(port, handler_cls):
        srv = real_bind(port, handler_cls)
        started["port"] = srv.server_address[1]
        # Patch serve_forever on this instance to be a no-op.
        srv.serve_forever = lambda: None  # type: ignore[method-assign]
        return srv

    monkeypatch.setattr(review_server, "_bind_server", fake_bind)
    try:
        review_server.serve(tmp_path, port=busy_port, open_browser=False)
    finally:
        blocker.close()

    assert "port" in started
    # Must have bound to a different (ephemeral) port.
    assert started["port"] != busy_port
    assert started["port"] != 0


def test_post_confirm_triggers_shutdown_flag(tmp_path, monkeypatch):
    # Seed a valid bundle.json so do_POST with empty body works.
    (tmp_path / "bundle.json").write_text(json.dumps(valid_bundle()))

    shutdown_calls: list[bool] = []

    class _FS(_FakeServer):
        def shutdown(self):
            shutdown_calls.append(True)

    h, sent = _make_handler(tmp_path, {"Content-Length": "0"})
    h.server = _FS()
    h.path = "/confirm"

    # Stub wfile so flush() doesn't error.
    h.wfile = MagicMock()

    # Patch time.sleep inside server module so the test doesn't actually wait.
    monkeypatch.setattr(review_server.time, "sleep", lambda _s: None)

    h.do_POST()
    # Response was sent.
    assert sent and sent[0][0] == 200
    # Derived artifacts written.
    assert (tmp_path / "skills.json").exists()
    # The shutdown thread should have run by now; join via a brief retry.
    import time as _t
    for _ in range(50):
        if shutdown_calls:
            break
        _t.sleep(0.01)
    assert shutdown_calls == [True]
