from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ultra_plan._timeout import DEFAULT_TIMEOUT, resolve_timeout
from ultra_plan.cli import main

from .fixtures import valid_bundle


def test_resolve_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ULTRA_PLAN_TIMEOUT", raising=False)
    assert resolve_timeout(None) == DEFAULT_TIMEOUT


def test_resolve_timeout_env_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ULTRA_PLAN_TIMEOUT", "42")
    assert resolve_timeout(None) == 42


def test_resolve_timeout_explicit_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ULTRA_PLAN_TIMEOUT", "42")
    assert resolve_timeout(99) == 99


def test_resolve_timeout_zero_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ULTRA_PLAN_TIMEOUT", raising=False)
    assert resolve_timeout(0) is None


def test_resolve_timeout_invalid_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ULTRA_PLAN_TIMEOUT", "not-a-number")
    with pytest.raises(RuntimeError, match="must be an integer"):
        resolve_timeout(None)


def test_execute_headless_passes_timeout_to_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))

    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr("subprocess.run", mock_run)

    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude",
        "--headless", "--yes",
        "--timeout", "60",
    ])
    assert rc == 0
    assert mock_run.call_args.kwargs.get("timeout") == 60


def test_execute_headless_subprocess_timeout_surfaces_friendly_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["claude"], timeout=5)

    monkeypatch.setattr("subprocess.run", _raise_timeout)

    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude",
        "--headless", "--yes",
        "--timeout", "5",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "timed out" in captured.err
    assert "5s" in captured.err
