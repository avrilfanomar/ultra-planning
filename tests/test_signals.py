from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultra_plan.cli import main

from .fixtures import valid_bundle


def test_keyboard_interrupt_in_execute_returns_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))

    def _raise_sigint(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("subprocess.run", _raise_sigint)

    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude",
        "--headless", "--yes",
    ])
    assert rc == 130
    captured = capsys.readouterr()
    assert "aborted" in captured.err.lower()


def test_keyboard_interrupt_in_review_server_exits_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))

    # Make serve_forever raise KeyboardInterrupt to simulate Ctrl-C while serving.
    import ultra_plan.review.server as srv

    class _FakeServer:
        server_address = ("127.0.0.1", 0)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    fake = _FakeServer()
    monkeypatch.setattr(srv, "_bind_server", lambda port, handler: fake)

    # Should NOT raise — KeyboardInterrupt is caught inside serve().
    srv.serve(bundle_dir, port=0, open_browser=False)
    assert fake.closed is True
