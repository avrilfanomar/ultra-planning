from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def _build_tool_list(tools: list[dict]) -> list[str]:
    """Extract tool names/patterns from the tools list for --allowedTools."""
    tool_names = []
    for tool in tools:
        if tool.get("enabled", True) is False:
            continue
        name = tool.get("name", "")
        kind = tool.get("kind", "")

        # For MCP servers, use the mcp__ prefix pattern
        if kind == "mcp":
            tool_names.append(f"mcp__{name}__*")
        # For regular tools, use the name directly
        elif name:
            tool_names.append(name)

    return tool_names


def _build_execution_prompt(bundle: dict) -> str:
    """Build the execution prompt from bundle components."""
    task = bundle.get("task", "")
    prompt_recs = bundle.get("prompt_recommendations", "")
    expected_outcome = bundle.get("expected_outcome", "")
    plan = bundle.get("plan_markdown", "")

    parts = []

    if prompt_recs:
        parts.append("# Instructions\n")
        parts.append(prompt_recs)
        parts.append("\n")

    if expected_outcome:
        parts.append("# Expected Outcome\n")
        parts.append(expected_outcome)
        parts.append("\n")

    if plan:
        parts.append("# Plan\n")
        parts.append(plan)
        parts.append("\n")

    parts.append("# Task\n")
    parts.append(task)

    return "\n".join(parts)


def _write_temp_settings(permissions: dict) -> Path:
    """Write a temporary settings.json with the bundle permissions."""
    temp_dir = Path(tempfile.mkdtemp(prefix="ultra-plan-exec-"))
    settings_file = temp_dir / "settings.json"

    # Build a minimal settings structure with the permissions
    settings = {
        "permissions": permissions
    }

    settings_file.write_text(json.dumps(settings, indent=2))
    return settings_file


def execute_claude(bundle: dict, *, interactive: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Execute a task using the Claude CLI with bundle configuration.

    Args:
        bundle: The ultra-plan bundle containing task, tools, permissions, etc.
        interactive: If True, run interactively. If False, run headless with --output-format json.
        cwd: Working directory for the execution (defaults to current directory).

    Returns:
        The completed subprocess result.
    """
    # Build the execution prompt
    prompt = _build_execution_prompt(bundle)

    # Build tool allowlist
    tools = bundle.get("tools", [])
    tool_list = _build_tool_list(tools)

    # Build base command
    cmd = ["claude", "-p"]

    if not interactive:
        cmd.extend(["--output-format", "json"])

    # Add allowed tools if any
    if tool_list:
        cmd.extend(["--allowedTools", ",".join(tool_list)])

    # Prepare environment
    env = os.environ.copy()

    # Handle permissions by writing a temporary settings file
    permissions = bundle.get("permissions", {})
    settings_file = None
    if permissions:
        settings_file = _write_temp_settings(permissions)
        # Note: Claude CLI doesn't have a --settings flag, so we'd need to
        # either modify ~/.claude/settings.json or use CLAUDE_SETTINGS_PATH
        # For now, just log the settings location
        print(f"[ultra-plan] Generated settings at: {settings_file}")
        print(f"[ultra-plan] Note: You may need to manually apply permissions from this file")

    print(f"[ultra-plan] Executing with {len(tool_list)} allowed tools")
    print(f"[ultra-plan] Command: {' '.join(cmd)}")

    try:
        if interactive:
            # For interactive mode, use stdin for prompt and let user interact
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                check=True,
                env=env,
                cwd=cwd,
            )
        else:
            # For non-interactive mode, capture output
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                check=True,
                env=env,
                cwd=cwd,
            )
        return proc
    except FileNotFoundError as e:
        raise RuntimeError("claude CLI not found on PATH - install Claude Code") from e
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "")[-500:] if hasattr(e, "stderr") else ""
        raise RuntimeError(
            f"claude CLI failed with exit code {e.returncode}: {stderr_tail}"
        ) from e
    finally:
        # Clean up temp settings file
        if settings_file and settings_file.parent.exists():
            try:
                settings_file.unlink()
                settings_file.parent.rmdir()
            except Exception:
                pass


def execute_opencode(bundle: dict, *, interactive: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Execute a task using the opencode CLI with bundle configuration.

    Args:
        bundle: The ultra-plan bundle containing task, tools, permissions, etc.
        interactive: If True, run interactively. If False, run headless.
        cwd: Working directory for the execution (defaults to current directory).

    Returns:
        The completed subprocess result.
    """
    # Build the execution prompt
    prompt = _build_execution_prompt(bundle)

    # opencode run takes prompt as positional arg
    cmd = ["opencode", "run"]

    if not interactive:
        cmd.append("--dangerously-skip-permissions")

    cmd.extend(["--", prompt])

    print(f"[ultra-plan] Executing with opencode")
    print(f"[ultra-plan] Command: opencode run -- <prompt>")

    try:
        if interactive:
            proc = subprocess.run(
                cmd,
                text=True,
                check=True,
                cwd=cwd,
            )
        else:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=cwd,
            )
        return proc
    except FileNotFoundError as e:
        raise RuntimeError("opencode CLI not found on PATH - install opencode") from e
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "")[-500:] if hasattr(e, "stderr") else ""
        raise RuntimeError(
            f"opencode CLI failed with exit code {e.returncode}: {stderr_tail}"
        ) from e


def execute_bundle(
    bundle_dir: Path,
    *,
    agent: str = "claude",
    interactive: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Execute a bundle using the specified agent.

    Args:
        bundle_dir: Directory containing bundle.json and derived artifacts.
        agent: Agent to use ('claude' or 'opencode').
        interactive: If True, run interactively. If False, run headless.
        cwd: Working directory for the execution (defaults to bundle_dir).

    Returns:
        The completed subprocess result.
    """
    bundle_file = bundle_dir / "bundle.json"
    if not bundle_file.exists():
        raise FileNotFoundError(f"No bundle.json found at {bundle_dir}")

    bundle = json.loads(bundle_file.read_text())

    # Default to bundle directory as working directory
    if cwd is None:
        cwd = bundle_dir

    if agent == "claude":
        return execute_claude(bundle, interactive=interactive, cwd=cwd)
    elif agent == "opencode":
        return execute_opencode(bundle, interactive=interactive, cwd=cwd)
    else:
        raise ValueError(f"Unknown agent: {agent}")
