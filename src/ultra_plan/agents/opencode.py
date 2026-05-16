from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ._env import scrub_env
from ._errors import classify_cli_error
from ._extract import extract_bundle

# Strict preflight config. opencode discovers config in the working dir / git
# root, so we drop this into the sandbox tempdir and run from there.
# `allowed_tools` from the caller is enforced via this materialized policy
# rather than per-invocation CLI flags (opencode has no equivalent of
# claude's --allowedTools).
_PREFLIGHT_CONFIG: dict = {
    "$schema": "https://opencode.ai/config.json",
    "permission": {
        "*": "deny",
        "read": "deny",
        "edit": "deny",
        "write": "deny",
        "bash": "deny",
        "webfetch": "allow",
        "websearch": "allow",
        "external_directory": "deny",
    },
}


def run(prompt: str, *, allowed_tools: list[str]) -> dict:
    # `allowed_tools` is enforced via the materialized opencode.json policy,
    # not via CLI flags. Accepted for interface parity with the claude agent.
    del allowed_tools
    with tempfile.TemporaryDirectory(prefix="ultra-plan-preflight-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "opencode.json").write_text(json.dumps(_PREFLIGHT_CONFIG))

        cmd = ["opencode", "run"]
        env = scrub_env(os.environ)

        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                check=True,
                env=env,
                cwd=tmp_path,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "opencode CLI not found on PATH - install opencode"
            ) from e
        except subprocess.CalledProcessError as e:
            raise classify_cli_error(e, cli_name="opencode") from e
        return extract_bundle(proc.stdout)
