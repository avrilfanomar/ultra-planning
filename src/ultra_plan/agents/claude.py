from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ._env import scrub_env
from ._errors import classify_cli_error
from ._extract import extract_bundle

# Static defense-in-depth deny list applied to the preflight planning run.
# Holds even if a caller passes a broader allowed_tools list.
_PREFLIGHT_SETTINGS: dict = {
    "permissions": {
        "deny": [
            "Read",
            "Write",
            "Edit",
            "NotebookEdit",
            "Bash",
            "WebFetch(file://*)",
            "WebFetch(http://localhost*)",
            "WebFetch(http://127.0.0.1*)",
            "WebFetch(http://169.254.169.254*)",
        ],
    },
}


def run(prompt: str, *, allowed_tools: list[str]) -> dict:
    # Pipe the prompt via stdin rather than positional argv so that prompts
    # beginning with "-" can never be misinterpreted as CLI flags. The `-p`
    # flag without a value tells claude to read the user message from stdin.
    with tempfile.TemporaryDirectory(prefix="ultra-plan-preflight-") as tmp:
        tmp_path = Path(tmp)
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(_PREFLIGHT_SETTINGS))

        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--settings",
            str(settings_file),
            "--allowedTools",
            ",".join(allowed_tools),
        ]

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
                "claude CLI not found on PATH - install Claude Code"
            ) from e
        except subprocess.CalledProcessError as e:
            raise classify_cli_error(e, cli_name="claude") from e

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return extract_bundle(proc.stdout)
        text = _extract_assistant_text(envelope)
        return extract_bundle(text)


def _extract_assistant_text(envelope: object) -> str:
    if isinstance(envelope, dict):
        for key in ("result", "response", "text", "output", "content"):
            v = envelope.get(key)
            if isinstance(v, str) and v:
                return v
        if "messages" in envelope and isinstance(envelope["messages"], list):
            chunks: list[str] = []
            for m in envelope["messages"]:
                if isinstance(m, dict):
                    c = m.get("content")
                    if isinstance(c, str):
                        chunks.append(c)
                    elif isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                chunks.append(part["text"])
            if chunks:
                return "\n".join(chunks)
        keys = sorted(envelope.keys())
        raise RuntimeError(
            "Could not locate assistant text in claude envelope; "
            f"unknown shape with top-level keys: {keys}"
        )
    raise RuntimeError(
        f"Unexpected claude envelope type: {type(envelope).__name__}"
    )
