from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .agent_setup import build_claude_settings, build_opencode_config, build_skills_context
from .agents._env import scrub_env
from .agents._errors import classify_cli_error


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
        cfg, skipped = build_claude_settings(bundle)
        if skipped:
            print(
                "[ultra-plan] warning: MCP tools missing transport, skipped: "
                + ", ".join(skipped)
            )
        if not cfg:
            return None
        dest = bundle_dir / "settings.json"
        dest.write_text(json.dumps(cfg, indent=2))
        return dest
    elif agent == "opencode":
        cfg, skipped = build_opencode_config(bundle)
        if skipped:
            print(
                "[ultra-plan] warning: MCP tools missing transport, skipped: "
                + ", ".join(skipped)
            )
        # Only write when there is content beyond the bare $schema key
        if not any(k != "$schema" for k in cfg):
            return None
        dest = bundle_dir / "opencode.json"
        dest.write_text(json.dumps(cfg, indent=2))
        return dest
    return None


def _build_execute_env(pass_env: list[str] | None) -> dict[str, str]:
    """Build a scrubbed environment for execute, plus opt-in passthroughs.

    Reuses the preflight allowlist via ``scrub_env`` and additionally keeps
    any variable named in ``pass_env`` (when present in the parent env).
    """
    base = scrub_env(os.environ)
    if pass_env:
        for var in pass_env:
            if var in os.environ:
                base[var] = os.environ[var]
    return base


def _write_headless_capture(bundle_dir: Path, proc: subprocess.CompletedProcess) -> Path:
    """Persist captured stdout/stderr from a headless run into bundle_dir.

    Stdout is written as ``execute-result.json`` when valid JSON, otherwise
    ``execute-result.txt``. Stderr (when present) is written to
    ``execute-stderr.log``. Returns the result file path.
    """
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    try:
        json.loads(stdout)
        result_path = bundle_dir / "execute-result.json"
    except (json.JSONDecodeError, ValueError):
        result_path = bundle_dir / "execute-result.txt"
    result_path.write_text(stdout)

    if stderr:
        (bundle_dir / "execute-stderr.log").write_text(stderr)

    return result_path


def execute_claude(
    bundle: dict,
    *,
    interactive: bool = True,
    cwd: Path | None = None,
    bundle_dir: Path | None = None,
    pass_env: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Execute a task using the Claude CLI with bundle configuration.

    Args:
        bundle: The ultra-plan bundle containing task, tools, permissions, etc.
        interactive: If True, run interactively. If False, run headless with --print and --output-format json.
        cwd: Working directory for the execution (defaults to current directory).
        bundle_dir: Bundle directory; used to discover a materialized settings.json
            and to write captured headless stdout/stderr.
        pass_env: Optional list of environment variable names to pass through
            in addition to the scrubbed allowlist.

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

    # In headless mode use `-p` (read prompt from stdin); in interactive mode we
    # keep positional argv because piping stdin would steal the user's TTY.
    if not interactive:
        cmd.append("-p")
        cmd.extend(["--output-format", "json"])

    # Add allowed tools if any
    if tool_list:
        cmd.extend(["--allowedTools", ",".join(tool_list)])

    # Use materialized settings.json from bundle_dir if available
    if bundle_dir is not None:
        settings_file = bundle_dir / "settings.json"
        if settings_file.exists():
            cmd.extend(["--settings", str(settings_file)])

    # Prepare environment (scrubbed + opt-in passthrough)
    env = _build_execute_env(pass_env)

    print(f"[ultra-plan] Executing with {len(tool_list)} allowed tools")

    try:
        if interactive:
            # Interactive sessions need a real TTY: stdin is reserved for the
            # user, so we pass the prompt as a positional argument instead.
            print(f"[ultra-plan] Command: {' '.join(cmd)} <prompt>")
            cmd.append(prompt)
            proc = subprocess.run(
                cmd,
                text=True,
                check=True,
                env=env,
                cwd=cwd,
            )
            return proc
        # Headless mode: feed prompt via stdin so it can never be mistaken for
        # a CLI flag, even if it begins with "-".
        print(f"[ultra-plan] Command: {' '.join(cmd)} (prompt via stdin)")
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
            env=env,
            cwd=cwd,
        )
        if bundle_dir is not None:
            result_path = _write_headless_capture(bundle_dir, proc)
            print(f"[ultra-plan] Wrote execute output to {result_path}")
        return proc
    except FileNotFoundError as e:
        raise RuntimeError("claude CLI not found on PATH - install Claude Code") from e
    except subprocess.CalledProcessError as e:
        # Best-effort: still persist any captured output for post-mortem.
        if bundle_dir is not None and not interactive:
            try:
                _write_headless_capture(bundle_dir, e)  # type: ignore[arg-type]
            except Exception:
                pass
        raise classify_cli_error(e, cli_name="claude") from e


def execute_opencode(
    bundle: dict,
    *,
    interactive: bool = True,
    cwd: Path | None = None,
    bundle_dir: Path | None = None,
    pass_env: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Execute a task using the opencode CLI with bundle configuration.

    Args:
        bundle: The ultra-plan bundle containing task, tools, permissions, etc.
        interactive: If True, run interactively. If False, run headless with --dangerously-skip-permissions.
        cwd: Working directory for the execution (defaults to current directory).
        bundle_dir: Bundle directory; when set, persists captured headless output here.
        pass_env: Optional list of environment variable names to pass through
            in addition to the scrubbed allowlist.

    Returns:
        The completed subprocess result.
    """
    # Build the execution prompt
    prompt = _build_execution_prompt(bundle)

    cmd = ["opencode", "run"]

    if not interactive:
        cmd.append("--dangerously-skip-permissions")
        cmd.extend(["--format", "json"])

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
                dest = cwd / "opencode.json"
                src_bytes = opencode_cfg.read_bytes()
                if dest.exists():
                    try:
                        dest_bytes = dest.read_bytes()
                    except OSError:
                        dest_bytes = b""
                    if dest_bytes != src_bytes:
                        ts = time.strftime("%Y%m%d-%H%M%S")
                        backup = cwd / f"opencode.json.bak.{ts}"
                        shutil.copy(str(dest), str(backup))
                        print(
                            f"[ultra-plan] warning: existing opencode.json at {dest} "
                            f"backed up to {backup} before overwrite"
                        )
                shutil.copy(str(opencode_cfg), str(dest))

    env = _build_execute_env(pass_env)

    print("[ultra-plan] Executing with opencode")

    try:
        if interactive:
            # Interactive sessions need a TTY; pass the prompt positionally
            # using `--` so it can't be parsed as a flag.
            print("[ultra-plan] Command: opencode run -- <prompt>")
            interactive_cmd = list(cmd) + ["--", prompt]
            proc = subprocess.run(
                interactive_cmd,
                text=True,
                check=True,
                env=env,
                cwd=effective_cwd,
            )
            return proc
        # Headless: feed prompt via stdin (parity with claude headless).
        print(f"[ultra-plan] Command: {' '.join(cmd)} (prompt via stdin)")
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
            env=env,
            cwd=effective_cwd,
        )
        if bundle_dir is not None:
            result_path = _write_headless_capture(bundle_dir, proc)
            print(f"[ultra-plan] Wrote execute output to {result_path}")
        return proc
    except FileNotFoundError as e:
        raise RuntimeError("opencode CLI not found on PATH - install opencode") from e
    except subprocess.CalledProcessError as e:
        if bundle_dir is not None and not interactive:
            try:
                _write_headless_capture(bundle_dir, e)  # type: ignore[arg-type]
            except Exception:
                pass
        raise classify_cli_error(e, cli_name="opencode") from e


def _confirmation_summary(bundle: dict, *, agent: str, cwd: Path | None) -> str:
    """Render a human-readable summary of what `execute` is about to run."""
    tools = bundle.get("tools", [])
    tool_list = _build_tool_list(tools)
    mcp_names = [t.get("name", "") for t in tools if t.get("kind") == "mcp" and t.get("enabled", True) is not False]

    lines = [
        "[ultra-plan] About to execute:",
        f"  agent: {agent}",
        f"  cwd: {cwd if cwd is not None else os.getcwd()}",
        f"  allowed tools ({len(tool_list)}): {', '.join(tool_list[:10])}"
        + (" ..." if len(tool_list) > 10 else ""),
        f"  MCP servers: {', '.join(mcp_names) if mcp_names else '(none)'}",
    ]
    return "\n".join(lines)


def execute_bundle(
    bundle_dir: Path,
    *,
    agent: str = "claude",
    interactive: bool = True,
    cwd: Path | None = None,
    pass_env: list[str] | None = None,
    yes: bool = False,
) -> subprocess.CompletedProcess:
    """Execute a bundle using the specified agent.

    Args:
        bundle_dir: Directory containing bundle.json and derived artifacts.
        agent: Agent to use ('claude' or 'opencode').
        interactive: If True, run interactively. If False, run headless.
        cwd: Working directory for the execution (defaults to bundle_dir).
        pass_env: Optional list of environment variable names to pass through
            to the executing agent in addition to the scrubbed default set.
        yes: If True, skip the interactive confirmation prompt. Required in
            headless mode.

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

    # Headless runs must be explicitly approved up-front.
    if not interactive and not yes:
        raise RuntimeError(
            "headless execute requires --yes to confirm; refusing to launch "
            "an agent unattended without explicit approval"
        )

    # Interactive confirmation gate.
    if interactive and not yes:
        print(_confirmation_summary(bundle, agent=agent, cwd=cwd))
        try:
            answer = input("Proceed? [y/N] ").strip()
        except EOFError:
            answer = ""
        if answer not in {"y", "Y"}:
            print("[ultra-plan] Aborted by user.", file=sys.stderr)
            raise RuntimeError("execute aborted by user")

    if agent == "claude":
        return execute_claude(
            bundle,
            interactive=interactive,
            cwd=cwd,
            bundle_dir=bundle_dir,
            pass_env=pass_env,
        )
    elif agent == "opencode":
        return execute_opencode(
            bundle,
            interactive=interactive,
            cwd=cwd,
            bundle_dir=bundle_dir,
            pass_env=pass_env,
        )
    else:
        raise ValueError(f"Unknown agent: {agent}")
