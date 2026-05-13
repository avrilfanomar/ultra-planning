from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .orchestrator import default_out_dir, review_existing, run_plan
from .prompts import resolve_sources

_SUBCOMMANDS = {"run", "review"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ultra-plan", description="Ultra planning over web sources.")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the full ultra-plan flow.")
    run.add_argument("task", help="The task to plan for.")
    run.add_argument("--agent", choices=["claude", "opencode"], default="claude")
    run.add_argument("--sources", default=None, help="Comma-separated: github,mcp,anthropic,web")
    run.add_argument("--preset", default="wide", help="Preset to use when --sources is unset.")
    run.add_argument("--out", default=None, help="Output directory.")
    run.add_argument("--port", type=int, default=7777)
    run.add_argument("--no-browser", action="store_true")

    rev = sub.add_parser("review", help="Re-open the review UI for an existing bundle.")
    rev.add_argument("dir", help="Bundle directory.")
    rev.add_argument("--port", type=int, default=7777)
    rev.add_argument("--no-browser", action="store_true")

    return p


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    if argv[0] in {"-h", "--help"}:
        return argv
    if argv[0] in _SUBCOMMANDS:
        return argv
    return ["run", *argv]


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(_normalize_argv(raw))

    if args.command == "review":
        review_existing(Path(args.dir), port=args.port, open_browser=not args.no_browser)
        return 0

    sources = resolve_sources(args.sources, args.preset)
    out = Path(args.out) if args.out else default_out_dir(args.task)
    run_plan(
        args.task,
        agent=args.agent,
        sources=sources,
        out_dir=out,
        port=args.port,
        open_browser=not args.no_browser,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
