from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.fixtures import valid_bundle
from ultra_plan.cli import main


def test_cwd_inside_bundle_dir_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))
    inner = bundle_dir / "sub"
    inner.mkdir()

    monkeypatch.setattr("subprocess.run", MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr="")))
    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude", "--headless", "--yes",
        "--cwd", str(inner),
    ])
    assert rc == 0


def test_cwd_outside_bundle_dir_refused_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude", "--headless", "--yes",
        "--cwd", str(outside),
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "outside bundle directory" in captured.err
    assert "--allow-external-cwd" in captured.err


def test_cwd_outside_bundle_dir_allowed_with_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    monkeypatch.setattr("subprocess.run", MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr="")))
    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude", "--headless", "--yes",
        "--allow-external-cwd",
        "--cwd", str(outside),
    ])
    assert rc == 0
