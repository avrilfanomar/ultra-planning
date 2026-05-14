from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ultra_plan.cli import main
from tests.fixtures import valid_bundle


def test_execute_command_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Integration test: execute command reads bundle and invokes agent CLI."""
    # Prepare a bundle directory
    bundle_dir = tmp_path / "test-bundle"
    bundle_dir.mkdir()
    bundle = valid_bundle()
    (bundle_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    # Mock subprocess.run to capture the command
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr("subprocess.run", mock_run)

    # Run the execute command
    result = main(["execute", str(bundle_dir), "--agent", "claude", "--headless"])

    # Verify command execution
    assert result == 0
    assert mock_run.called
    call_args = mock_run.call_args

    # Verify command structure
    cmd = call_args[0][0]
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "--allowedTools" in cmd

    # Verify tool configuration
    tools_idx = cmd.index("--allowedTools")
    tools = cmd[tools_idx + 1]
    assert "mcp__postgres-mcp__*" in tools

    # Verify prompt was passed correctly
    kwargs = call_args[1]
    prompt = kwargs.get("input", "")
    assert bundle["task"] in prompt
    assert bundle["prompt_recommendations"] in prompt
    assert bundle["expected_outcome"] in prompt
    assert bundle["plan_markdown"] in prompt


def test_execute_with_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test execute command with opencode agent."""
    bundle_dir = tmp_path / "test-bundle"
    bundle_dir.mkdir()
    bundle = valid_bundle()
    (bundle_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr("subprocess.run", mock_run)

    result = main(["execute", str(bundle_dir), "--agent", "opencode", "--headless"])

    assert result == 0
    assert mock_run.called

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "opencode"
    assert "run" in cmd
    assert "--dangerously-skip-permissions" in cmd


def test_execute_missing_bundle(tmp_path: Path, capsys):
    """Test execute command fails gracefully when bundle.json is missing."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="No bundle.json found"):
        main(["execute", str(empty_dir)])


def test_execute_with_custom_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test execute command respects --cwd flag."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundle = valid_bundle()
    (bundle_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0)
    monkeypatch.setattr("subprocess.run", mock_run)

    result = main([
        "execute",
        str(bundle_dir),
        "--agent", "claude",
        "--headless",
        "--cwd", str(work_dir)
    ])

    assert result == 0
    # Verify cwd was passed to subprocess
    kwargs = mock_run.call_args[1]
    assert kwargs.get("cwd") == work_dir
