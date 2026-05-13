from __future__ import annotations

from ultra_plan.prompts import render_prompt, resolve_sources


def test_render_includes_only_selected_sources():
    prompt = render_prompt("build a thing", ["github", "web"])
    assert "## Source: github" in prompt
    assert "## Source: web" in prompt
    assert "## Source: mcp" not in prompt
    assert "## Source: anthropic" not in prompt
    assert "build a thing" in prompt


def test_render_no_sources():
    prompt = render_prompt("t", [])
    assert "## Source:" not in prompt
    assert "t" in prompt


def test_resolve_sources_explicit_overrides_preset():
    assert resolve_sources("github,web", "wide") == ["github", "web"]


def test_resolve_sources_preset_wide():
    assert resolve_sources(None, "wide") == ["github", "mcp", "anthropic", "web"]


def test_resolve_sources_local_only():
    assert resolve_sources(None, "local-only") == []
