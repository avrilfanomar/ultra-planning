from __future__ import annotations

import pytest

from ultra_plan.cli import _build_parser, _normalize_argv


def test_default_subcommand_inserted():
    assert _normalize_argv(["my task"]) == ["run", "my task"]


def test_explicit_subcommand_kept():
    assert _normalize_argv(["run", "x"]) == ["run", "x"]
    assert _normalize_argv(["review", "./dir"]) == ["review", "./dir"]


def test_run_parses_defaults():
    p = _build_parser()
    ns = p.parse_args(_normalize_argv(["build a thing"]))
    assert ns.command == "run"
    assert ns.task == "build a thing"
    assert ns.agent == "claude"
    assert ns.preset == "wide"
    assert ns.sources is None
    assert ns.port == 7777
    assert ns.no_browser is False
    assert ns.out is None


def test_run_parses_flags():
    p = _build_parser()
    ns = p.parse_args(_normalize_argv([
        "task", "--agent", "opencode",
        "--sources", "github,web",
        "--preset", "wide",
        "--out", "/tmp/x",
        "--port", "8000",
        "--no-browser",
    ]))
    assert ns.agent == "opencode"
    assert ns.sources == "github,web"
    assert ns.out == "/tmp/x"
    assert ns.port == 8000
    assert ns.no_browser is True


def test_invalid_agent_rejected():
    p = _build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(_normalize_argv(["task", "--agent", "bogus"]))


def test_review_subcommand():
    p = _build_parser()
    ns = p.parse_args(["review", "./out"])
    assert ns.command == "review"
    assert ns.dir == "./out"
