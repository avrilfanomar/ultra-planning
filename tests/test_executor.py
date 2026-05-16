from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures import valid_bundle
from ultra_plan.executor import (
    _build_execute_env,
    _build_execution_prompt,
    _build_tool_list,
    _materialize_agent_config,
    execute_bundle,
)


def test_build_tool_list():
    """Test that tool list is correctly extracted from bundle tools."""
    tools = [
        {"name": "postgres-mcp", "kind": "mcp", "enabled": True},
        {"name": "WebFetch", "kind": "tool", "enabled": True},
        {"name": "disabled-tool", "kind": "tool", "enabled": False},
        {"name": "another-mcp", "kind": "mcp"},  # enabled by default
    ]

    result = _build_tool_list(tools)

    assert "mcp__postgres-mcp__*" in result
    assert "WebFetch" in result
    assert "mcp__another-mcp__*" in result
    assert "disabled-tool" not in result
    assert len(result) == 3


def test_build_execution_prompt():
    """Test that execution prompt is correctly built from bundle."""
    bundle = {
        "task": "Build a REST API",
        "prompt_recommendations": "Use FastAPI framework",
        "expected_outcome": "API with OpenAPI docs",
        "plan_markdown": "## Plan\n1. Setup project\n2. Implement endpoints",
    }

    prompt = _build_execution_prompt(bundle)

    assert "Build a REST API" in prompt
    assert "Use FastAPI framework" in prompt
    assert "API with OpenAPI docs" in prompt
    assert "## Plan" in prompt
    assert "# Instructions" in prompt
    assert "# Expected Outcome" in prompt
    assert "# Task" in prompt


def test_build_execution_prompt_minimal():
    """Test prompt building with only task field."""
    bundle = {"task": "Simple task"}

    prompt = _build_execution_prompt(bundle)

    assert "Simple task" in prompt
    assert "# Task" in prompt


def test_execute_bundle_missing_file(tmp_path: Path):
    """Test that execute_bundle raises error when bundle.json is missing."""
    with pytest.raises(FileNotFoundError, match="No bundle.json found"):
        execute_bundle(tmp_path, agent="claude", yes=True)


def test_execute_bundle_invalid_agent(tmp_path: Path):
    """Test that execute_bundle raises error for unknown agent."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps(valid_bundle()))

    with pytest.raises(ValueError, match="Unknown agent"):
        execute_bundle(tmp_path, agent="invalid-agent", yes=True)


def test_execute_bundle_creates_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that execute_bundle prepares the correct prompt and pipes it via stdin in headless mode."""
    bundle_file = tmp_path / "bundle.json"
    bundle = valid_bundle()
    bundle_file.write_text(json.dumps(bundle))

    # Track subprocess calls
    calls = []

    def mock_run(*args, **kwargs):
        calls.append((args, kwargs))

        class MockProc:
            returncode = 0
            stdout = ""
            stderr = ""

        return MockProc()

    monkeypatch.setattr("subprocess.run", mock_run)

    execute_bundle(tmp_path, agent="claude", interactive=False, yes=True)

    assert len(calls) == 1
    args, kwargs = calls[0]
    cmd = args[0]

    # Headless claude uses -p (read prompt from stdin), not --print + positional prompt.
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--allowedTools" in cmd

    tool_arg_idx = cmd.index("--allowedTools")
    tools_str = cmd[tool_arg_idx + 1]
    assert "mcp__postgres-mcp__*" in tools_str

    # Prompt must be piped via stdin in headless mode, NOT appended to argv.
    prompt_input = kwargs.get("input")
    assert prompt_input is not None
    assert bundle["task"] in prompt_input
    assert bundle["prompt_recommendations"] in prompt_input
    assert bundle["task"] not in cmd  # prompt must not be in argv

    # settings.json should be written into the bundle directory (not a temp dir)
    settings_file = tmp_path / "settings.json"
    assert settings_file.exists()
    settings = json.loads(settings_file.read_text())
    assert "permissions" in settings


def test_materialize_agent_config_claude(tmp_path: Path):
    """_materialize_agent_config writes settings.json for claude."""
    bundle = valid_bundle()
    result = _materialize_agent_config(bundle, tmp_path, "claude")
    assert result is not None
    assert result == tmp_path / "settings.json"
    assert result.exists()
    data = json.loads(result.read_text())
    assert "permissions" in data


def test_materialize_agent_config_opencode(tmp_path: Path):
    """_materialize_agent_config writes opencode.json for opencode."""
    bundle = valid_bundle()
    result = _materialize_agent_config(bundle, tmp_path, "opencode")
    assert result is not None
    assert result == tmp_path / "opencode.json"
    assert result.exists()
    data = json.loads(result.read_text())
    assert "$schema" in data


def test_materialize_agent_config_no_content_returns_none(tmp_path: Path):
    """When bundle has no permissions/mcp, no file is written for claude."""
    bundle = {"task": "x"}
    result = _materialize_agent_config(bundle, tmp_path, "claude")
    assert result is None
    assert not (tmp_path / "settings.json").exists()


def test_headless_requires_yes(tmp_path: Path):
    """Headless mode without --yes refuses to launch."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps(valid_bundle()))

    with pytest.raises(RuntimeError, match="--yes"):
        execute_bundle(tmp_path, agent="claude", interactive=False, yes=False)


def test_build_execute_env_scrubs_secrets(monkeypatch: pytest.MonkeyPatch):
    """Default env passed to execute drops secrets and keeps allowlist."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _build_execute_env(None)

    assert "PATH" in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "AWS_ACCESS_KEY_ID" not in env


def test_build_execute_env_pass_env_opts_in(monkeypatch: pytest.MonkeyPatch):
    """--pass-env entries are forwarded even when normally scrubbed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _build_execute_env(["ANTHROPIC_API_KEY"])

    assert env.get("ANTHROPIC_API_KEY") == "sk-secret"
    # Vars not listed remain scrubbed
    assert "GITHUB_TOKEN" not in env


def test_build_execute_env_pass_env_unset_is_ignored(monkeypatch: pytest.MonkeyPatch):
    """Naming a var via --pass-env that isn't set is harmless."""
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    env = _build_execute_env(["DOES_NOT_EXIST"])
    assert "DOES_NOT_EXIST" not in env


def test_execute_bundle_writes_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Headless run persists stdout/stderr into bundle_dir."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps(valid_bundle()))

    captured_stdout = '{"ok": true}'
    captured_stderr = "warn: something"

    def mock_run(*args, **kwargs):
        class MockProc:
            returncode = 0
            stdout = captured_stdout
            stderr = captured_stderr

        return MockProc()

    monkeypatch.setattr("subprocess.run", mock_run)

    execute_bundle(tmp_path, agent="claude", interactive=False, yes=True)

    result_path = tmp_path / "execute-result.json"
    assert result_path.exists()
    assert result_path.read_text() == captured_stdout

    stderr_path = tmp_path / "execute-stderr.log"
    assert stderr_path.exists()
    assert stderr_path.read_text() == captured_stderr


def test_execute_bundle_capture_non_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Non-JSON stdout is captured to execute-result.txt."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps(valid_bundle()))

    def mock_run(*args, **kwargs):
        class MockProc:
            returncode = 0
            stdout = "plain text output"
            stderr = ""

        return MockProc()

    monkeypatch.setattr("subprocess.run", mock_run)

    execute_bundle(tmp_path, agent="claude", interactive=False, yes=True)

    assert (tmp_path / "execute-result.txt").exists()
    assert not (tmp_path / "execute-result.json").exists()


def test_execute_opencode_pipes_stdin_headless(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """opencode headless mode pipes prompt via stdin (no positional prompt argv)."""
    bundle_file = tmp_path / "bundle.json"
    bundle = valid_bundle()
    bundle_file.write_text(json.dumps(bundle))

    calls = []

    def mock_run(*args, **kwargs):
        calls.append((args, kwargs))

        class MockProc:
            returncode = 0
            stdout = ""
            stderr = ""

        return MockProc()

    monkeypatch.setattr("subprocess.run", mock_run)

    execute_bundle(tmp_path, agent="opencode", interactive=False, yes=True)

    args, kwargs = calls[0]
    cmd = args[0]
    assert cmd[0] == "opencode"
    assert "run" in cmd
    # No `--` separator nor positional prompt in argv
    assert "--" not in cmd
    assert bundle["task"] not in cmd
    # Prompt arrives via stdin
    assert kwargs.get("input") is not None
    assert bundle["task"] in kwargs["input"]
