from __future__ import annotations

import json
import shutil
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"

MAX_BODY = 10 * 1024 * 1024  # 10 MiB hard cap on request body.


def _validate_or_error(bundle: dict) -> str | None:
    from ..validate import validate_bundle
    from jsonschema import ValidationError

    try:
        validate_bundle(bundle)
        return None
    except ValidationError as e:
        return e.message


def _enabled(items: list) -> list:
    return [i for i in items if i.get("enabled", True) is not False]


def write_derived_artifacts(out_dir: Path, bundle: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))
    (out_dir / "skills.json").write_text(json.dumps(_enabled(bundle.get("skills", [])), indent=2))
    (out_dir / "tools.json").write_text(json.dumps(_enabled(bundle.get("tools", [])), indent=2))
    (out_dir / "permissions.json").write_text(json.dumps(bundle.get("permissions", {}), indent=2))
    (out_dir / "plan.md").write_text(bundle.get("plan_markdown", ""))
    (out_dir / "prompt-recommendations.md").write_text(bundle.get("prompt_recommendations", ""))
    (out_dir / "expected-outcome.md").write_text(bundle.get("expected_outcome", ""))


def copy_static(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "app.js", "style.css"):
        src = STATIC_DIR / name
        if src.exists():
            shutil.copy(src, out_dir / name)


class _Handler(BaseHTTPRequestHandler):
    out_dir: Path = Path(".")

    def log_message(self, format: str, *args: object) -> None:  # silence
        return

    def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
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
        port = self.server.server_address[1]
        return origin in (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        )

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            return self._serve_static("index.html", "text/html; charset=utf-8")
        if self.path == "/app.js":
            return self._serve_static("app.js", "application/javascript")
        if self.path == "/style.css":
            return self._serve_static("style.css", "text/css")
        if self.path == "/bundle":
            data = (self.out_dir / "bundle.json").read_bytes()
            return self._send(200, data)
        return self._send(404, b'{"error":"not found"}')

    def _serve_static(self, name: str, ctype: str) -> None:
        path = self.out_dir / name
        if not path.exists():
            path = STATIC_DIR / name
        self._send(200, path.read_bytes(), ctype)

    def do_PUT(self) -> None:
        if self.path != "/bundle":
            return self._send(404, b'{"error":"not found"}')
        if not self._check_origin():
            return self._send(403, json.dumps({"error": "forbidden origin"}).encode())
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
        (self.out_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))
        self._send(200, b'{"ok":true}')

    def do_POST(self) -> None:
        if self.path != "/confirm":
            return self._send(404, b'{"error":"not found"}')
        if not self._check_origin():
            return self._send(403, json.dumps({"error": "forbidden origin"}).encode())
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
            (self.out_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))
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

        def _delayed_shutdown(srv) -> None:
            time.sleep(0.1)
            srv.shutdown()

        threading.Thread(
            target=_delayed_shutdown, args=(self.server,), daemon=True
        ).start()


def serve(out_dir: Path, port: int, open_browser: bool = True) -> None:
    out_dir = out_dir.resolve()
    copy_static(out_dir)
    handler = type("BoundHandler", (_Handler,), {"out_dir": out_dir})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"[ultra-plan] review UI: {url}")
    if open_browser:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
