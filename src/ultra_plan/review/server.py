from __future__ import annotations

import errno
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .._io import atomic_write_text
from .._logging import get_logger
from ._ratelimit import TokenBucket

log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

MAX_BODY = 10 * 1024 * 1024  # 10 MiB hard cap on request body.

# Placeholder substituted into index.html at serve-time so the page receives
# a per-run token. See `_serve_index_html` below.
_TOKEN_PLACEHOLDER = "__ULTRA_PLAN_TOKEN__"

# Strict CSP: same-origin only; no inline scripts/styles; no eval; no framing.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)

_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", _CSP),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cache-Control", "no-store"),
)


# Re-export under the old private name so external/test imports don't break.
_atomic_write_text = atomic_write_text


def _validate_or_error(bundle: dict) -> str | None:
    from jsonschema import ValidationError

    from ..validate import format_validation_error, validate_bundle

    try:
        validate_bundle(bundle)
        return None
    except ValidationError as e:
        return format_validation_error(e)


def _enabled(items: list) -> list:
    return [i for i in items if i.get("enabled", True) is not False]


def write_derived_artifacts(out_dir: Path, bundle: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(out_dir / "bundle.json", json.dumps(bundle, indent=2))
    _atomic_write_text(
        out_dir / "skills.json", json.dumps(_enabled(bundle.get("skills", [])), indent=2)
    )
    _atomic_write_text(
        out_dir / "tools.json", json.dumps(_enabled(bundle.get("tools", [])), indent=2)
    )
    _atomic_write_text(out_dir / "plan.md", bundle.get("plan_markdown", ""))
    _atomic_write_text(
        out_dir / "prompt-recommendations.md", bundle.get("prompt_recommendations", "")
    )
    _atomic_write_text(out_dir / "expected-outcome.md", bundle.get("expected_outcome", ""))


def copy_static(out_dir: Path) -> None:
    """Deprecated no-op kept for backward compatibility.

    Review-UI assets (index.html/app.js/style.css) are now served directly
    from the package's STATIC_DIR. We intentionally no longer copy them into
    the user's --out directory so UI assets do not get mixed with bundle
    artifacts. Callers (e.g. orchestrator.py) may still invoke this; keeping
    the function as a no-op avoids a breaking change.
    """
    return None


class _Handler(BaseHTTPRequestHandler):
    out_dir: Path = Path(".")
    token: str = ""
    ratelimiter: TokenBucket | None = None

    def log_message(self, format: str, *args: object) -> None:  # silence
        return

    def _check_rate_limit(self) -> bool:
        if self.ratelimiter is None:
            return True
        client_ip = self.client_address[0] if self.client_address else "unknown"
        return self.ratelimiter.check(client_ip)

    def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes | None:
        """Read the request body. Returns None if Content-Length exceeds MAX_BODY.

        Callers should respond 413 when None is returned rather than raising.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > MAX_BODY:
            return None
        return self.rfile.read(length) if length else b""

    def _check_origin(self) -> bool:
        """Allow same-origin (or no-Origin) requests only, to block CSRF.

        The Origin header is optional; same-origin form posts often omit it.
        When present, it must match http://127.0.0.1:<port> or
        http://localhost:<port> where <port> is the server's bound port.
        """
        origin = self.headers.get("Origin")
        if not origin:
            return True
        addr = self.server.server_address
        port = addr[1] if isinstance(addr, tuple) else 0
        return origin in (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        )

    def _check_token(self) -> bool:
        """Verify the per-run CSRF token.

        Accepts the token via the `X-Ultra-Plan-Token` header (preferred) or a
        `?token=` query parameter. If the server was started without a token
        (e.g. in tests that don't go through `serve()`), this check is a no-op.
        """
        if not self.token:
            return True
        provided = self.headers.get("X-Ultra-Plan-Token", "")
        if not provided:
            qs = urlsplit(self.path).query
            params = parse_qs(qs)
            provided = (params.get("token") or [""])[0]
        return secrets.compare_digest(provided, self.token)

    def do_GET(self) -> None:
        # Strip query string for routing.
        route = urlsplit(self.path).path
        if route in ("/", "/index.html"):
            return self._serve_index_html()
        if route == "/app.js":
            return self._serve_static("app.js", "application/javascript")
        if route == "/style.css":
            return self._serve_static("style.css", "text/css")
        if route == "/bundle":
            data = (self.out_dir / "bundle.json").read_bytes()
            return self._send(200, data)
        return self._send(404, b'{"error":"not found"}')

    def _serve_static(self, name: str, ctype: str) -> None:
        """Serve a static asset directly from the package STATIC_DIR."""
        path = STATIC_DIR / name
        self._send(200, path.read_bytes(), ctype)

    def _serve_index_html(self) -> None:
        """Serve index.html dynamically, substituting the per-run token.

        We do the substitution at request time rather than copying a rewritten
        copy into out_dir so UI assets stay in the package and the token never
        touches disk in the user's --out directory.
        """
        html = (STATIC_DIR / "index.html").read_text()
        html = html.replace(_TOKEN_PLACEHOLDER, self.token)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def do_PUT(self) -> None:
        if urlsplit(self.path).path != "/bundle":
            return self._send(404, b'{"error":"not found"}')
        if not self._check_origin():
            return self._send(403, json.dumps({"error": "forbidden origin"}).encode())
        if not self._check_token():
            return self._send(403, json.dumps({"error": "forbidden token"}).encode())
        if not self._check_rate_limit():
            return self._send(429, json.dumps({"error": "rate limit exceeded"}).encode())
        body = self._read_body()
        if body is None:
            return self._send(413, json.dumps({"error": "request body too large"}).encode())
        try:
            bundle = json.loads(body or b"{}")
        except json.JSONDecodeError as e:
            return self._send(400, json.dumps({"error": str(e)}).encode())
        err = _validate_or_error(bundle)
        if err is not None:
            return self._send(400, json.dumps({"error": err}).encode())
        _atomic_write_text(self.out_dir / "bundle.json", json.dumps(bundle, indent=2))
        self._send(200, b'{"ok":true}')

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/confirm":
            return self._send(404, b'{"error":"not found"}')
        if not self._check_origin():
            return self._send(403, json.dumps({"error": "forbidden origin"}).encode())
        if not self._check_token():
            return self._send(403, json.dumps({"error": "forbidden token"}).encode())
        if not self._check_rate_limit():
            return self._send(429, json.dumps({"error": "rate limit exceeded"}).encode())
        body = self._read_body()
        if body is None:
            return self._send(413, json.dumps({"error": "request body too large"}).encode())
        if body:
            try:
                bundle = json.loads(body)
            except json.JSONDecodeError as e:
                return self._send(400, json.dumps({"error": str(e)}).encode())
            err = _validate_or_error(bundle)
            if err is not None:
                return self._send(400, json.dumps({"error": err}).encode())
            _atomic_write_text(self.out_dir / "bundle.json", json.dumps(bundle, indent=2))
        bundle = json.loads((self.out_dir / "bundle.json").read_text())
        write_derived_artifacts(self.out_dir, bundle)
        self._send(200, b'{"ok":true}')
        # Make sure the response is fully flushed before initiating shutdown.
        # `server.shutdown()` blocks until the serve loop exits, so we must
        # call it from a different thread; we sleep briefly first so the
        # client receives the response cleanly before the socket is torn down.
        try:
            self.wfile.flush()
        except Exception:
            pass

        def _delayed_shutdown(srv: ThreadingHTTPServer) -> None:
            time.sleep(0.1)
            srv.shutdown()

        threading.Thread(
            target=_delayed_shutdown, args=(self.server,), daemon=True
        ).start()


def _max_inflight() -> int:
    raw = os.environ.get("ULTRA_PLAN_MAX_INFLIGHT")
    if not raw:
        return 8
    try:
        value = int(raw)
    except ValueError:
        return 8
    return max(1, value)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a hard cap on concurrent in-flight requests.

    When the bound is reached, additional requests are refused synchronously
    with HTTP 503 (no new worker thread is spawned). This prevents resource
    exhaustion from a flood of slow/parallel requests.
    """

    daemon_threads = True

    def __init__(self, *args: object, max_inflight: int | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        cap = max_inflight if max_inflight is not None else _max_inflight()
        self._inflight_sem = threading.BoundedSemaphore(cap)

    def process_request(self, request: object, client_address: object) -> None:
        if not self._inflight_sem.acquire(blocking=False):
            try:
                request.sendall(  # type: ignore[attr-defined]
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: 27\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                    b'{"error":"server busy"}\n'
                )
            except OSError:
                pass
            self.shutdown_request(request)  # type: ignore[arg-type]
            return

        def _wrapper() -> None:
            try:
                self.process_request_thread(request, client_address)  # type: ignore[arg-type]
            finally:
                self._inflight_sem.release()
                self.shutdown_request(request)  # type: ignore[arg-type]

        t = threading.Thread(target=_wrapper, daemon=self.daemon_threads)
        t.start()


def _bind_server(port: int, handler_cls: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    """Bind a BoundedThreadingHTTPServer on 127.0.0.1, falling back to an
    ephemeral port if the requested one is busy or unusable."""
    try:
        return BoundedThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, errno.EACCES):
            log.warning(
                "port %d unavailable (%s); binding to an ephemeral port",
                port,
                e.strerror or e,
            )
            return BoundedThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        raise


def serve(out_dir: Path, port: int, open_browser: bool = True) -> None:
    out_dir = out_dir.resolve()
    token = secrets.token_urlsafe(32)
    handler = type(
        "BoundHandler",
        (_Handler,),
        {"out_dir": out_dir, "token": token, "ratelimiter": TokenBucket()},
    )
    server = _bind_server(port, handler)
    bound_port = server.server_address[1]
    url = f"http://127.0.0.1:{bound_port}/"
    log.info("review UI: %s", url)
    if open_browser:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.warning("review server interrupted, shutting down")
    finally:
        server.server_close()
