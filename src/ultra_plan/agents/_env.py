from __future__ import annotations

"""Environment scrubbing for headless agent invocations.

The preflight planning agent runs against attacker-controlled web content,
so we strip the process environment down to the variables the CLI actually
needs to run and authenticate. Anything resembling a secret (``*_TOKEN``,
``*_KEY``, ``*_SECRET``, ``AWS_*``, ``GITHUB_*`` …) is dropped so a
prompt-injected agent cannot exfiltrate it via WebFetch URLs.
"""

ALLOWED_ENV_KEYS = frozenset({
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TERM",
    "LANG",
    "TZ",
    "TMPDIR",
})

ALLOWED_ENV_PREFIXES = ("CLAUDE_", "OPENCODE_", "LC_", "XDG_")


def scrub_env(env: dict[str, str]) -> dict[str, str]:
    return {
        k: v
        for k, v in env.items()
        if k in ALLOWED_ENV_KEYS or k.startswith(ALLOWED_ENV_PREFIXES)
    }
