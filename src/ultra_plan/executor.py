from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .agent_setup import build_claude_settings, build_opencode_config, build_skills_context


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

    # Prepend skills context when present
    skills_ctx = build_skills_context(bundle)
    if skills_ctx:
        parts.append(skills_ctx)
        parts.append("\n")

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


def _materialize_agent_config(bundle: dict, bundle_dir: Path, agent: str) -> Path | None:
    """Write agent configuration into *bundle_dir* and return the file path.

    Returns the written file's path, or None when nothing was written (e.g.
    the generated config carries no meaningful content beyond the $schema stub).
    """
    if agent == "claude":
        cfg = build_claude_settings(bundle)
        if not cfg:
            return None
        dest = bundle_dir / "settings.json"
        dest.write_text(json.dumps(cfg, indent=2))
        return dest
    elif agent == "opencode":
        cfg = build_opencode_config(bundle)
        # Only write when there is content beyond the bare $schema key
        if not any(k != "$schema" for k in cfg):
            return None
        dest = bundle_dir / "opencode.json"
        dest.write_text(json.dumps(cfg, indent=2))
        return dest
    return None


def execute_claude(bundle: dict, *, interactive: bool = True, cwd: Path | None = None, bundle_dir: Path | None = None) -> subprocess.CompletedProcess:
    """Execute a task using the Claude CLI with bundle configuration.

    Args:
        bundle: The ultra-plan bundle containing task, tools, permissions, etc.
        interactive: If True, run interactively. If False, run headless with --print and --output-format json.
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
    cmd = ["claude"]

    # Add print flag for non-interactive mode
    if not interactive:
        cmd.append("--print")
        cmd.extend(["--output-format", "json"])

    # Add allowed tools if any
    if tool_list:
        cmd.extend(["--allowedTools", ",".join(tool_list)])

    # Use materialized settings.json from bundle_dir if available
    if bundle_dir is not None:
        settings_file = bundle_dir / "settings.json"
        if settings_file.exists():
            cmd.extend(["--settings", str(settings_file)])

    # Prepare environment
    env = os.environ.copy()

    print(f"[ultra-plan] Executing with {len(tool_list)} allowed tools")
    print(f"[ultra-plan] Command: {' '.join(cmd)} <prompt>")

    # Add prompt as the final positional argument
    cmd.append(prompt)

    try:
        if interactive:
            # For interactive mode, let user interact with the session
            proc = subprocess.run(
                cmd,
                text=True,
                check=True,
                env=env,
                cwd=cwd,
            )
        else:
            # For non-interactive mode, capture output
            proc = subprocess.run(
                cmd,
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


def execute_opencode(bundle: dict, *, interactive: bool = True, cwd: Path | None = None, bundle_dir: Path | None = None) -> subprocess.CompletedProcess:
    """Execute a task using the opencode CLI with bundle configuration.

    Args:
        bundle: The ultra-plan bundle containing task, tools, permissions, etc.
        interactive: If True, run interactively. If False, run headless with --dangerously-skip-permissions.
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
        cmd.extend(["--format", "json"])

    # Add prompt as positional argument (using -- separator for safety)
    cmd.append("--")
    cmd.append(prompt)

    print(f"[ultra-plan] Executing with opencode")
    print(f"[ultra-plan] Command: opencode run -- <prompt>")

    # Determine effective cwd and ensure opencode.json is discoverable.
    # When no explicit cwd is given, run from bundle_dir so opencode picks up
    # opencode.json via its "current dir → git root" lookup.
    # When an explicit cwd is given, copy opencode.json there first.
    effective_cwd = cwd
    if bundle_dir is not None:
        opencode_cfg = bundle_dir / "opencode.json"
        if opencode_cfg.exists():
            if cwd is None:
                effective_cwd = bundle_dir
            elif cwd.resolve() != bundle_dir.resolve():
                # Copy opencode.json to the explicit cwd so opencode discovers it
                shutil.copy(str(opencode_cfg), str(cwd / "opencode.json"))

    try:
        if interactive:
            proc = subprocess.run(
                cmd,
                text=True,
                check=True,
                cwd=effective_cwd,
            )
        else:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                cwd=effective_cwd,
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

    # Materialize agent-specific config files into bundle_dir before launching.
    _materialize_agent_config(bundle, bundle_dir, agent)

    # Default to bundle directory as working directory
    if cwd is None:
        cwd = bundle_dir

    if agent == "claude":
        return execute_claude(bundle, interactive=interactive, cwd=cwd, bundle_dir=bundle_dir)
    elif agent == "opencode":
        return execute_opencode(bundle, interactive=interactive, cwd=cwd, bundle_dir=bundle_dir)
    else:
        raise ValueError(f"Unknown agent: {agent}")
