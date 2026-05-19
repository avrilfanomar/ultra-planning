# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-19

### Added
- Stdlib `logging` foundation with top-level `--quiet`/`--verbose`/`--debug` flags inherited by every subcommand. All informational and warning output is now structured and routed through the `logging` module.
- `--timeout SECONDS` flag on `execute` plus `ULTRA_PLAN_TIMEOUT` env override (default 1800s; 0 disables). Preflight agents also honour the timeout.
- Friendly JSON-pointer-aware validation errors via `validate.format_validation_error()` and `validate_bundle_friendly()`. Bundle validation failures now report the failing path and the offending value instead of a raw `jsonschema` traceback.
- Exponential-backoff retry with jitter for transient preflight agent failures (HTTP 429, `ECONNRESET`, timeout signals). Only the planning preflight is retried; the interactive `execute` path is not.
- `--allow-external-cwd` opt-in flag on `execute`. By default `--cwd` must be within the bundle directory; the flag is required to override.
- `SECURITY.md` with a private vulnerability disclosure policy, threat-model summary, and supported-versions table.
- Security response headers on every review-server response: `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Cache-Control: no-store`.
- `BoundedThreadingHTTPServer`: caps in-flight requests via a bounded semaphore (default 8, override with `ULTRA_PLAN_MAX_INFLIGHT`); excess requests are refused with HTTP 503 without spawning a worker thread.
- Per-IP token-bucket rate limiter on review-server `PUT`/`POST`; excess requests are answered with HTTP 429.
- `KeyboardInterrupt` handling at the CLI level returns exit code 130 cleanly; the review server now exits gracefully on Ctrl-C.
- New GitHub workflow `codeql.yml` running CodeQL on push, pull-request, and a weekly cron.
- `.github/dependabot.yml` watching `pip` and `github-actions` ecosystems weekly.
- `.pre-commit-config.yaml` with `ruff`, `ruff-format`, hygiene hooks, and a local `mypy` hook.
- Type-check CI job running `mypy` against `src/ultra_plan` with `disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, `check_untyped_defs`, `warn_unused_ignores`.
- Coverage gate enforced at 80% (branch coverage) via `pytest-cov`; coverage artifact uploaded from the canonical CI run.
- macOS and Windows on Python 3.12 added to the CI matrix (Linux still covers 3.10/3.11/3.12).
- Release workflow: SBOM (`cyclonedx-bom`) generated and bundled with build artifacts; PyPI Trusted Publishing now requests artifact attestations. All `actions/*` and `pypa/*` references pinned by commit SHA.
- `_io.atomic_write_text` / `atomic_write_bytes` helper, reused by the review server and `execute` config materialization so a failed write cannot leave a `.tmp` artifact behind.

### Changed
- All `print("[ultra-plan] …")` informational lines in `executor.py`, `orchestrator.py`, `agent_setup.py`, and `review/server.py` are now `log.info`/`log.warning`. User-facing error lines on `stderr` and the interactive confirmation prompt are unchanged.
- `errno.EACCES` / `PermissionError` from missing CLIs or missing bundles surface as "permission denied: …" hints in addition to the existing "not found" path.
- `scrub_env` now accepts `collections.abc.Mapping[str, str]` (previously declared `dict[str, str]`), matching the actual `os.environ` shape.

### Security
- Review server binds only to `127.0.0.1` (existing behaviour, now covered by a regression test).
- Review server now sets a strict CSP with no inline scripts/styles, plus the usual hardening headers.
- Path-traversal guard on `--cwd` (see `--allow-external-cwd` above).
- Default subprocess timeout prevents hung preflight or `execute` runs.
- Bounded concurrency + per-IP rate limit shield the local review server from runaway client loops.

## [0.1.8] - 2026-05-17

### Fixed
- Fixed "Settings file not found" error when running `ultra-plan execute` from outside the bundle directory. All path arguments (`bundle_dir`, `cwd`) are now resolved to absolute paths before being passed to the agent CLI.

### Added
- Added test `test_execute_resolves_relative_paths` to verify that relative paths are properly resolved to absolute paths.

## [0.1.7] - 2026-05-17

### Fixed
- Fixed version mismatch between `pyproject.toml` (0.1.6) and `__init__.py` (0.1.4).

### Added
- Added `test_version.py` to automatically detect version inconsistencies between `pyproject.toml` and `__init__.py`.

## [0.1.2] - 2026-05-16

### Changed
- Sync `pyproject.toml` version to match the released tag.

## [0.1.0] - 2026-05-16

### Added
- `ultra-plan` CLI with `plan` and `execute` commands.
- Two-phase workflow: locked-down headless planning agent produces a reviewable bundle of skills, tools, MCP servers, and permission patches; `execute` materializes the approved bundle and launches the coding agent.
- Local review server (`review/`) for inspecting and approving the produced bundle before execution.
- Support for Claude Code and opencode headless agents (`agents/claude.py`, `agents/opencode.py`).
- Bundle schema validation (`schema/*.json`).
- Sample bundle under `examples/sample-bundle/`.
- Documentation: `docs/ARCHITECTURE.md`, `docs/EXECUTION_GUIDE.md`.
- GitHub Actions CI: pytest matrix on Python 3.10, 3.11, 3.12.

### Security
- Environment scrubbing for the planning agent: allowlist of env keys and prefixes strips secrets (`*_TOKEN`, `*_KEY`, `AWS_*`, `GITHUB_*`, …) before invoking the headless agent.
- Review server enforces a per-session token (header and query-param), origin checks, and a request body size limit (HTTP 413 over 10 MB).
- WebFetch preflight denies `file://`, `localhost`, `127.0.0.1`, and the AWS IMDS address `169.254.169.254`.
- Prompts are piped to agents via stdin to prevent argv flag injection.

[0.3.0]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.3.0
[0.1.8]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.1.8
[0.1.7]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.1.7
[0.1.2]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.1.2
[0.1.0]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.1.0
