from __future__ import annotations

import argparse
import errno
import sys
from pathlib import Path

from . import __version__
from ._logging import configure_logging, get_logger
from .executor import execute_bundle
from .orchestrator import default_out_dir, review_existing, run_plan
from .prompts import resolve_sources

_SUBCOMMANDS = {"run", "review", "execute"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ultra-plan", description="Ultra planning over web sources.")
    p.add_argument("-v", "--version", action="version", version=f"ultra-plan {__version__}")
    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument("-q", "--quiet", action="store_true", help="Suppress INFO logs.")
    verbosity.add_argument("--verbose", action="store_true", help="Enable DEBUG logs for ultra_plan.*")
    verbosity.add_argument("--debug", action="store_true", help="Enable DEBUG logs globally.")
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

    exe = sub.add_parser("execute", help="Execute a prepared bundle with the selected agent.")
    exe.add_argument("dir", help="Bundle directory containing bundle.json.")
    exe.add_argument("--agent", choices=["claude", "opencode"], default="claude")
    exe.add_argument("--headless", action="store_true", help="Run in non-interactive mode.")
    exe.add_argument("--cwd", default=None, help="Working directory for execution (defaults to bundle dir).")
    exe.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="VAR",
        help="Environment variable name to pass through to the agent in addition "
             "to the scrubbed default allowlist. Repeatable.",
    )
    exe.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt. Required with --headless.",
    )
    exe.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Headless subprocess timeout in seconds (default 1800; "
             "overridden by ULTRA_PLAN_TIMEOUT env). 0 disables.",
    )
    exe.add_argument(
        "--allow-external-cwd",
        action="store_true",
        help="Allow --cwd to point outside the bundle directory. By default "
             "the working directory must be within the bundle dir to prevent "
             "accidental execution against unrelated trees.",
    )

    return p


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    if argv[0] in {"-h", "--help", "-v", "--version"}:
        return argv
    if argv[0] in _SUBCOMMANDS:
        return argv
    return ["run", *argv]


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    args = parser.parse_args(_normalize_argv(raw))

    configure_logging(quiet=args.quiet, verbose=args.verbose, debug=args.debug)

    try:
        if args.command == "review":
            review_existing(Path(args.dir).resolve(), port=args.port, open_browser=not args.no_browser)
            return 0

        if args.command == "execute":
            bundle_dir = Path(args.dir).resolve()
            cwd = Path(args.cwd).resolve() if args.cwd else None
            if cwd is not None and not args.allow_external_cwd:
                if not cwd.is_relative_to(bundle_dir):
                    raise RuntimeError(
                        f"--cwd {cwd} is outside bundle directory {bundle_dir}; "
                        "pass --allow-external-cwd to override"
                    )
            execute_bundle(
                bundle_dir,
                agent=args.agent,
                interactive=not args.headless,
                cwd=cwd,
                pass_env=list(args.pass_env or []),
                yes=args.yes,
                timeout=args.timeout,
            )
            return 0

        sources = resolve_sources(args.sources, args.preset)
        out = Path(args.out).resolve() if args.out else default_out_dir(args.task).resolve()
        run_plan(
            args.task,
            agent=args.agent,
            sources=sources,
            out_dir=out,
            port=args.port,
            open_browser=not args.no_browser,
        )
        return 0
    except KeyboardInterrupt:
        get_logger(__name__).warning("aborted by user (SIGINT)")
        return 130
    except FileNotFoundError as e:
        # Missing CLI / missing bundle -> usage error
        if getattr(e, "errno", None) == errno.EACCES:
            print(f"error: permission denied: {e}", file=sys.stderr)
        else:
            print(f"error: {e}", file=sys.stderr)
        return 2
    except PermissionError as e:
        print(f"error: permission denied: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
