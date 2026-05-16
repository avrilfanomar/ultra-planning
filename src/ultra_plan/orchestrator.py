from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from .agents import claude as _claude
from .agents import opencode as _opencode
from .agents.claude import _PREFLIGHT_SETTINGS as _CLAUDE_PREFLIGHT_SETTINGS
from .agents.opencode import _PREFLIGHT_CONFIG as _OPENCODE_PREFLIGHT_CONFIG
from .prompts import render_prompt
from .review.server import copy_static, serve
from .validate import validate_bundle

AgentFn = Callable[..., dict]
AGENTS: dict[str, AgentFn] = {
    "claude": _claude.run,
    "opencode": _opencode.run,
}

DEFAULT_ALLOWED_TOOLS = ["WebSearch", "WebFetch"]


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "task"


def default_out_dir(task: str) -> Path:
    return Path("./ultra-plan") / slugify(task)


def run_plan(
    task: str,
    *,
    agent: str,
    sources: list[str],
    out_dir: Path,
    port: int,
    open_browser: bool,
) -> Path:
    if agent not in AGENTS:
        raise ValueError(f"Unknown agent: {agent}")
    print(f"[ultra-plan] agent={agent} sources={','.join(sources) or '(none)'}")
    prompt = render_prompt(task, sources)
    print(f"[ultra-plan] invoking {agent}...")
    bundle = AGENTS[agent](prompt, allowed_tools=DEFAULT_ALLOWED_TOOLS)
    bundle.setdefault("task", task)
    validate_bundle(bundle)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bundle.json").write_text(json.dumps(bundle, indent=2))

    # Persist the preflight settings used during planning for transparency
    if agent == "claude":
        (out_dir / "preflight-settings.json").write_text(
            json.dumps(_CLAUDE_PREFLIGHT_SETTINGS, indent=2)
        )
    elif agent == "opencode":
        (out_dir / "preflight-config.json").write_text(
            json.dumps(_OPENCODE_PREFLIGHT_CONFIG, indent=2)
        )

    copy_static(out_dir)
    print(f"[ultra-plan] bundle written to {out_dir}")
    serve(out_dir, port=port, open_browser=open_browser)
    return out_dir


def review_existing(out_dir: Path, *, port: int, open_browser: bool) -> None:
    if not (out_dir / "bundle.json").exists():
        raise FileNotFoundError(f"No bundle.json at {out_dir}")
    copy_static(out_dir)
    serve(out_dir, port=port, open_browser=open_browser)
