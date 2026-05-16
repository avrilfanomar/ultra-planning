# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.2]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.1.2
[0.1.0]: https://github.com/avrilfanomar/ultra-planning/releases/tag/v0.1.0
