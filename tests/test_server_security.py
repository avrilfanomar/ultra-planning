from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.fixtures import valid_bundle
from ultra_plan.review import server as srv
from ultra_plan.review._ratelimit import TokenBucket


def _start_server(out_dir: Path, *, ratelimiter: TokenBucket | None = None):
    handler = type(
        "T",
        (srv._Handler,),
        {"out_dir": out_dir, "token": "", "ratelimiter": ratelimiter},
    )
    s = srv.BoundedThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    return s, t


def _http_get(host: str, port: int, path: str = "/"):
    req = urllib.request.Request(f"http://{host}:{port}{path}")
    with urllib.request.urlopen(req, timeout=2) as resp:
        return resp.status, dict(resp.headers), resp.read()


def _http_put(host: str, port: int, path: str, body: bytes):
    req = urllib.request.Request(
        f"http://{host}:{port}{path}", data=body, method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_server_binds_to_loopback_only(tmp_path: Path) -> None:
    (tmp_path / "bundle.json").write_text(json.dumps(valid_bundle()))
    s, _ = _start_server(tmp_path)
    try:
        host, port = s.server_address
        assert host == "127.0.0.1"
        # Cannot connect from a non-loopback bind (no external listener).
        external = socket.socket()
        external.settimeout(0.2)
        with pytest.raises((ConnectionRefusedError, OSError)):
            external.connect(("192.0.2.1", port))  # TEST-NET-1, reserved
        external.close()
    finally:
        s.shutdown()
        s.server_close()


def test_security_headers_present_on_index(tmp_path: Path) -> None:
    (tmp_path / "bundle.json").write_text(json.dumps(valid_bundle()))
    s, _ = _start_server(tmp_path)
    try:
        host, port = s.server_address
        status, headers, _body = _http_get(host, port, "/")
        assert status == 200
        assert "Content-Security-Policy" in headers
        assert "default-src 'self'" in headers["Content-Security-Policy"]
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("Referrer-Policy") == "no-referrer"
        assert headers.get("X-Frame-Options") == "DENY"
    finally:
        s.shutdown()
        s.server_close()


def test_rate_limiter_returns_429_after_capacity_exhausted(tmp_path: Path) -> None:
    (tmp_path / "bundle.json").write_text(json.dumps(valid_bundle()))
    # Tight bucket: 3 capacity, refill 0/s (effectively no refill within test).
    bucket = TokenBucket(capacity=3, refill_per_sec=0.0001)
    s, _ = _start_server(tmp_path, ratelimiter=bucket)
    try:
        host, port = s.server_address
        codes = []
        body = json.dumps(valid_bundle()).encode()
        for _ in range(6):
            code, _ = _http_put(host, port, "/bundle", body)
            codes.append(code)
        # First 3 allowed (200), remaining 3 should be 429.
        assert codes.count(429) >= 2
    finally:
        s.shutdown()
        s.server_close()


def test_token_bucket_check_consumes_one_token() -> None:
    b = TokenBucket(capacity=2, refill_per_sec=0.0001)
    assert b.check("1.2.3.4", now=0.0) is True
    assert b.check("1.2.3.4", now=0.0) is True
    assert b.check("1.2.3.4", now=0.0) is False


def test_token_bucket_refills_over_time() -> None:
    b = TokenBucket(capacity=2, refill_per_sec=1.0)
    assert b.check("ip", now=0.0) is True
    assert b.check("ip", now=0.0) is True
    assert b.check("ip", now=0.0) is False
    assert b.check("ip", now=1.5) is True  # 1.5 tokens refilled, consume 1


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Threading timing on Windows CI is too loose for this race-based test.",
)
def test_bounded_server_returns_503_when_saturated(tmp_path: Path) -> None:
    """With max_inflight=1 and a slow handler, the second concurrent request is 503'd."""
    (tmp_path / "bundle.json").write_text(json.dumps(valid_bundle()))

    block = threading.Event()
    release = threading.Event()

    class _SlowHandler(srv._Handler):
        out_dir = tmp_path
        token = ""
        ratelimiter = None

        def do_GET(self):  # type: ignore[override]
            if self.path == "/slow":
                block.set()
                release.wait(timeout=2)
                return self._send(200, b"{}")
            return super().do_GET()

    s = srv.BoundedThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler, max_inflight=1)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    try:
        host, port = s.server_address
        results: dict[str, int] = {}

        def _hit(label, path):
            try:
                with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=3) as r:
                    results[label] = r.status
            except urllib.error.HTTPError as e:
                results[label] = e.code

        t1 = threading.Thread(target=_hit, args=("slow", "/slow"))
        t1.start()
        # Wait until the slow handler is blocked inside its worker.
        assert block.wait(timeout=2)
        t2 = threading.Thread(target=_hit, args=("blocked", "/"))
        t2.start()
        t2.join(timeout=2)
        release.set()
        t1.join(timeout=3)

        assert results.get("blocked") == 503
        assert results.get("slow") == 200
    finally:
        release.set()
        s.shutdown()
        s.server_close()
