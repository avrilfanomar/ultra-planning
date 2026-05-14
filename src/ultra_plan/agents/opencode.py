from __future__ import annotations

import subprocess

from ._extract import extract_bundle


def run(prompt: str, *, allowed_tools: list[str]) -> dict:
    # Pipe the prompt via stdin so a prompt starting with "-" can never be
    # misinterpreted as a CLI flag. `--dangerously-skip-permissions` keeps
    # the run non-interactive (opencode has no per-tool allowlist flag;
    # tool access is configured via agent definitions, not at runtime, so
    # `allowed_tools` is accepted for interface parity but not enforced here).
    del allowed_tools
    cmd = ["opencode", "run", "--dangerously-skip-permissions"]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, check=True
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "opencode CLI not found on PATH - install opencode"
        ) from e
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "")[-500:]
        raise RuntimeError(
            f"opencode CLI failed with exit code {e.returncode}: {stderr_tail}"
        ) from e
    return extract_bundle(proc.stdout)
