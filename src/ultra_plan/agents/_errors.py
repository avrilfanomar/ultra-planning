from __future__ import annotations

"""Shared error-classification for headless agent subprocess failures.

Both the claude and opencode planning agents surface authentication / rate-
limit / forbidden failures using the same wording so callers (and tests) can
match on a stable vocabulary.
"""

import json
import subprocess


def _extract_error_detail(exc: subprocess.CalledProcessError) -> str:
    """Pull a useful error message out of a CalledProcessError."""
    error_detail = ""
    stdout = getattr(exc, "stdout", "") or ""
    stderr = getattr(exc, "stderr", "") or ""

    if stdout:
        try:
            result = json.loads(stdout)
            if isinstance(result, dict) and "result" in result:
                error_detail = result["result"]
        except json.JSONDecodeError:
            pass

    if not error_detail:
        stderr_tail = stderr[-500:]
        stdout_tail = stdout[-500:]
        error_detail = stderr_tail or stdout_tail

    return error_detail


def classify_cli_error(
    exc: subprocess.CalledProcessError, *, cli_name: str
) -> RuntimeError:
    """Map a subprocess failure to a user-facing RuntimeError.

    Recognises 401 (auth), 403 (forbidden), 429 (rate limit) signatures
    in stdout/stderr and returns a tailored message; otherwise returns a
    generic "<cli> CLI failed with exit code N: <detail>" RuntimeError.
    """
    error_detail = _extract_error_detail(exc)
    low = error_detail.lower()

    if "Invalid API key" in error_detail or "401" in error_detail:
        return RuntimeError(
            f"{cli_name} CLI failed: Invalid API key. "
            f"Please authenticate with Claude Code using '/login' or 'claude auth'. "
            f"Error: {error_detail}"
        )
    if "403" in error_detail or "Forbidden" in error_detail:
        return RuntimeError(
            f"{cli_name} CLI failed: Permission denied. "
            f"Check your API key permissions. Error: {error_detail}"
        )
    if "429" in error_detail or "rate limit" in low:
        return RuntimeError(
            f"{cli_name} CLI failed: Rate limit exceeded. "
            f"Please try again later. Error: {error_detail}"
        )
    return RuntimeError(
        f"{cli_name} CLI failed with exit code {exc.returncode}: {error_detail}"
    )
