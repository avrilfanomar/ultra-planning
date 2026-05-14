from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultra_plan.executor import _build_tool_list, _build_execution_prompt, execute_bundle, _materialize_agent_config
from tests.fixtures import valid_bundle


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
        execute_bundle(tmp_path, agent="claude")


def test_execute_bundle_invalid_agent(tmp_path: Path):
    """Test that execute_bundle raises error for unknown agent."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps(valid_bundle()))

    with pytest.raises(ValueError, match="Unknown agent"):
        execute_bundle(tmp_path, agent="invalid-agent")


def test_execute_bundle_creates_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that execute_bundle prepares the correct prompt."""
    bundle_file = tmp_path / "bundle.json"
    bundle = valid_bundle()
    bundle_file.write_text(json.dumps(bundle))

    # Track subprocess calls
    calls = []

    def mock_run(*args, **kwargs):
        calls.append((args, kwargs))
        # Mock successful completion
        class MockProc:
            returncode = 0
            stdout = ""
            stderr = ""

        return MockProc()

    monkeypatch.setattr("subprocess.run", mock_run)

    # Execute bundle
    execute_bundle(tmp_path, agent="claude", interactive=False)

    # Verify subprocess was called
    assert len(calls) == 1
    args, kwargs = calls[0]
    cmd = args[0]

    # Verify command structure
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--output-format" in cmd
    assert "json" in cmd
    assert "--allowedTools" in cmd

    # Verify tools are configured
    tool_arg_idx = cmd.index("--allowedTools")
    tools_str = cmd[tool_arg_idx + 1]
    assert "mcp__postgres-mcp__*" in tools_str

    # Verify prompt contains bundle content (passed as last argument)
    prompt = cmd[-1]
    assert bundle["task"] in prompt
    assert bundle["prompt_recommendations"] in prompt

    # settings.json should be written into the bundle directory (not a temp dir)
    settings_file = tmp_path / "settings.json"
    assert settings_file.exists(), "settings.json should be written into bundle_dir"
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
