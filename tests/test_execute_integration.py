from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.fixtures import valid_bundle
from ultra_plan.cli import main


def test_execute_command_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Integration test: execute command reads bundle and invokes agent CLI via stdin."""
    bundle_dir = tmp_path / "test-bundle"
    bundle_dir.mkdir()
    bundle = valid_bundle()
    (bundle_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr("subprocess.run", mock_run)

    result = main(["execute", str(bundle_dir), "--agent", "claude", "--headless", "--yes"])

    assert result == 0
    assert mock_run.called
    call_args = mock_run.call_args

    cmd = call_args[0][0]
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "--allowedTools" in cmd

    tools_idx = cmd.index("--allowedTools")
    tools = cmd[tools_idx + 1]
    assert "mcp__postgres-mcp__*" in tools

    # Prompt should now be piped via stdin, not appended as final argv.
    prompt_input = call_args.kwargs.get("input")
    assert prompt_input is not None
    assert bundle["task"] in prompt_input
    assert bundle["prompt_recommendations"] in prompt_input
    assert bundle["expected_outcome"] in prompt_input
    assert bundle["plan_markdown"] in prompt_input

    assert bundle["task"] not in cmd

    assert (bundle_dir / "settings.json").exists()


def test_execute_with_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test execute command with opencode agent."""
    bundle_dir = tmp_path / "test-bundle"
    bundle_dir.mkdir()
    bundle = valid_bundle()
    (bundle_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr("subprocess.run", mock_run)

    result = main(["execute", str(bundle_dir), "--agent", "opencode", "--headless", "--yes"])

    assert result == 0
    assert mock_run.called

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "opencode"
    assert "run" in cmd
    assert "--dangerously-skip-permissions" in cmd

    assert (bundle_dir / "opencode.json").exists()


def test_execute_missing_bundle(tmp_path: Path, capsys):
    """Execute command exits 2 with a clean error when bundle.json is missing."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    rc = main(["execute", str(empty_dir), "--headless", "--yes"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "No bundle.json" in captured.err


def test_execute_with_custom_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test execute command respects --cwd flag."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundle = valid_bundle()
    (bundle_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr("subprocess.run", mock_run)

    result = main([
        "execute",
        str(bundle_dir),
        "--agent", "claude",
        "--headless",
        "--yes",
        "--cwd", str(work_dir),
    ])

    assert result == 0
    kwargs = mock_run.call_args[1]
    assert kwargs.get("cwd") == work_dir


def test_execute_headless_without_yes_exits_nonzero(tmp_path: Path, capsys):
    """Headless without --yes must fail with a clear error."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))

    rc = main(["execute", str(bundle_dir), "--headless"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "--yes" in captured.err


def test_execute_pass_env_flag_threaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--pass-env values reach the subprocess env."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps(valid_bundle()))

    monkeypatch.setenv("MY_SECRET", "shhh")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")

    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr("subprocess.run", mock_run)

    rc = main([
        "execute", str(bundle_dir),
        "--agent", "claude",
        "--headless", "--yes",
        "--pass-env", "MY_SECRET",
    ])
    assert rc == 0
    env = mock_run.call_args.kwargs["env"]
    assert env["MY_SECRET"] == "shhh"
    # ANTHROPIC_API_KEY was NOT passed through (not in --pass-env)
    assert "ANTHROPIC_API_KEY" not in env
