from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures import valid_bundle
from ultra_plan import orchestrator
from ultra_plan.agents._extract import extract_bundle
from ultra_plan.review.server import write_derived_artifacts


def test_run_plan_writes_artifacts(tmp_path: Path, monkeypatch):
    captured = {}

    def fake_run(prompt: str, *, allowed_tools: list[str]) -> dict:
        captured["prompt"] = prompt
        captured["allowed_tools"] = allowed_tools
        return valid_bundle()

    monkeypatch.setitem(orchestrator.AGENTS, "claude", fake_run)
    monkeypatch.setattr(orchestrator, "serve", lambda *a, **kw: None)

    out = tmp_path / "out"
    orchestrator.run_plan(
        "demo task",
        agent="claude",
        sources=["github", "web"],
        out_dir=out,
        port=7777,
        open_browser=False,
    )

    assert "## Source: github" in captured["prompt"]
    assert "## Source: mcp" not in captured["prompt"]
    assert (out / "bundle.json").exists()
    assert (out / "preflight-settings.json").exists()
    # UI assets (index.html/app.js/style.css) are served from the package's
    # STATIC_DIR and intentionally not copied into out_dir.
    assert not (out / "index.html").exists()
    # Derived artifacts are written only on Confirm via the review server.
    assert not (out / "skills.json").exists()

    bundle = json.loads((out / "bundle.json").read_text())
    assert bundle["task"] == "demo"  # fixture's task wins; setdefault only fills if missing
    assert len(bundle["skills"]) == 1

    # Verify preflight settings were persisted with expected deny list
    preflight = json.loads((out / "preflight-settings.json").read_text())
    assert "permissions" in preflight
    assert "deny" in preflight["permissions"]
    assert "Read" in preflight["permissions"]["deny"]
    assert "Write" in preflight["permissions"]["deny"]
    assert "Bash" in preflight["permissions"]["deny"]


def test_run_plan_writes_opencode_preflight(tmp_path: Path, monkeypatch):
    def fake_run(prompt: str, *, allowed_tools: list[str]) -> dict:
        return valid_bundle()

    monkeypatch.setitem(orchestrator.AGENTS, "opencode", fake_run)
    monkeypatch.setattr(orchestrator, "serve", lambda *a, **kw: None)

    out = tmp_path / "out"
    orchestrator.run_plan(
        "demo task",
        agent="opencode",
        sources=[],
        out_dir=out,
        port=7777,
        open_browser=False,
    )

    assert (out / "bundle.json").exists()
    assert (out / "preflight-config.json").exists()

    # Verify preflight config has strict deny defaults
    config = json.loads((out / "preflight-config.json").read_text())
    assert config["permission"]["read"] == "deny"
    assert config["permission"]["write"] == "deny"
    assert config["permission"]["bash"] == "deny"
    assert config["permission"]["webfetch"] == "allow"


def test_write_derived_artifacts_filters_disabled(tmp_path: Path):
    bundle = valid_bundle()
    bundle["skills"].append({**bundle["skills"][0], "name": "off", "enabled": False})
    write_derived_artifacts(tmp_path, bundle)
    skills = json.loads((tmp_path / "skills.json").read_text())
    assert [s["name"] for s in skills] == ["python-skill"]
    assert (tmp_path / "plan.md").read_text() == bundle["plan_markdown"]


def test_slugify():
    assert orchestrator.slugify("Build a Postgres + Slack bot!!") == "build-a-postgres-slack-bot"
    assert orchestrator.slugify("") == "task"


def test_extract_bundle_roundtrip():
    text = (
        "preamble\n===BUNDLE-BEGIN===\n"
        + json.dumps({"a": 1})
        + "\n===BUNDLE-END===\ntrailer"
    )
    assert extract_bundle(text) == {"a": 1}


def test_extract_bundle_handles_fenced_block():
    text = "===BUNDLE-BEGIN===\n```json\n{\"a\": 2}\n```\n===BUNDLE-END==="
    assert extract_bundle(text) == {"a": 2}
