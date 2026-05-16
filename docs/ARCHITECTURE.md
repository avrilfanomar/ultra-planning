# Architecture

Ultra-plan is a CLI that delegates discovery to a headless coding agent (Claude Code or Opencode) and produces a **reviewable bundle** of skills, tools, MCP servers, permissions, and prompt recommendations for a task. The bundle is then executed by the same agent under user-approved permissions.

The design splits the work into two phases with a human gate between them:

```
ultra-plan run "<task>"      →   bundle.json   →   ultra-plan execute <dir>
  (discovery, locked down)       (reviewed)         (task implementation)
```

## Two-phase flow

### Phase 1: planning (`run`)

```
task ──▶ render prompt ──▶ headless agent ──▶ raw bundle ──▶ validate
                          (preflight perms,                       │
                           WebSearch/Fetch                        ▼
                           only)                          write bundle.json
                                                          + serve review UI
```

1. `cli.py` parses flags, resolves sources (`github`, `mcp`, `anthropic`, `web`), renders the prompt template from `prompts/system.md` + `prompts/sources/*.md`.
2. `orchestrator.run_plan()` invokes the agent CLI via subprocess (`claude -p --output-format json` or `opencode run --dangerously-skip-permissions`). Allowed tools are restricted to `WebSearch` and `WebFetch`; preflight denies `Read`, `Write`, `Edit`, `NotebookEdit`, `Bash`, and `WebFetch` against `file://`, localhost, loopback, and IMDS endpoints.
3. The agent searches and ranks resources, returning a JSON bundle (`agents/_extract.py` parses it out of the output).
4. `validate.py` checks the bundle against the schema; `review/server.py` writes `bundle.json` and serves the static review UI at `http://localhost:7777`.
5. On confirm, derived `.md`/`.json` files (skills, tools, permissions, plan, expected-outcome, prompt-recommendations) are written as views of the bundle.

### Phase 2: execution (`execute`)

```
bundle.json ──▶ materialize config ──▶ build prompt ──▶ build tool allowlist ──▶ launch agent
              (settings.json or       (skills +          (mcp__<name>__*         (subprocess)
               opencode.json)          instructions +     or exact names)
                                       outcome + plan
                                       + task)
```

1. `executor.execute_bundle()` loads `bundle.json`.
2. `agent_setup.build_claude_settings()` / `build_opencode_config()` maps permissions and MCP tools (with `command`/`url`) into the agent's config format, written into the bundle directory.
3. The execution prompt is assembled in this order: `# Skills` → `# Instructions` (from `prompt_recommendations`) → `# Expected Outcome` → `# Plan` → `# Task`.
4. The tool allowlist is built from enabled tools: MCP tools become `mcp__<name>__*` wildcards; built-ins keep their exact name.
5. The agent CLI is launched. Working directory defaults to the bundle directory; `--cwd` overrides it (config file path is still passed explicitly to Claude via `--settings`; for Opencode it is copied to the custom cwd so config discovery works).
6. `--headless` switches to non-interactive JSON output for CI/automation.

## Design principles

**Thin orchestrator.** `cli.py` and `orchestrator.py` parse arguments, render prompts, invoke the agent via subprocess, and validate output. They contain no discovery logic, no agent reasoning, and no global config writes. Complexity lives in the agent CLIs.

**Bundle as the single source of truth.** `bundle.json` is the only canonical artifact. Review UI reads it directly. Derived files (`settings.json`, `opencode.json`, `*.md`) are regenerated on demand from the bundle; edit `bundle.json` and re-run `execute`.

**Write-only.** Ultra-plan never modifies `~/.claude/settings.json`, `~/.opencode/`, `$PATH`, or installs MCP servers/skills. It only writes inside the bundle directory. Install commands are surfaced for the user to run manually.

**Defense in depth.** Four independent layers gate what the agent can do:
1. Preflight permissions during planning (deny filesystem, shell, and private-network fetches).
2. Human review of the bundle before any code runs.
3. Tool allowlist passed to the agent CLI at execute time (`--allowedTools`).
4. The agent CLI's own permission enforcement from the materialized settings.

**Agent-agnostic bundle format.** The bundle's `permissions.allow/deny`, `tools[].kind` (`mcp`/`builtin`), and `tools[].command|url` are mapped per-agent at execute time. Adding a third agent means implementing `agents/<name>.py:run()`, `agent_setup.build_<name>_config()`, and registering it in `orchestrator.AGENTS` and the CLI choices.

## Bundle schema

```json
{
  "task": "string",
  "expected_outcome": "string",
  "skills": [
    {"name": "...", "source_url": "...", "origin": "anthropic|github|community",
     "install": "...", "rationale": "...", "enabled": true}
  ],
  "tools": [
    {"name": "...", "kind": "mcp|builtin", "source_url": "...",
     "command": ["npx", "-y", "..."], "url": null,
     "rationale": "...", "enabled": true}
  ],
  "permissions": {
    "allow": ["Write", "Edit", "Read", "Bash(python:*)"],
    "deny":  ["Bash(rm:*)", "Bash(sudo:*)"]
  },
  "plan_markdown": "## Step 1...",
  "prompt_recommendations": "- Follow PEP 8..."
}
```

## Module map

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing, command routing |
| `orchestrator.py` | `run_plan()`, `review_existing()`, agent registry |
| `executor.py` | `execute_bundle()` and per-agent execute helpers |
| `agent_setup.py` | Pure functions: `build_claude_settings()`, `build_opencode_config()`, `build_skills_context()` |
| `validate.py` | Bundle schema validation |
| `agents/claude.py`, `agents/opencode.py` | `run()`: subprocess invocation with preflight perms |
| `agents/_env.py` | `scrub_env()`: remove credentials before subprocess |
| `agents/_extract.py` | Parse bundle JSON out of agent output |
| `prompts/system.md`, `prompts/sources/*.md` | Prompt templates |
| `review/server.py`, `review/static/` | Local review server + static UI |

## Permission mapping (Claude → Opencode)

The bundle uses Claude-style permission strings. The opencode config builder maps them to coarse fields:

| Bundle pattern | Opencode field |
|---|---|
| `"Write"` in allow | `write: "allow"` |
| `"Edit"` in allow | `edit: "allow"` |
| `"Bash(...)"` in allow | `bash: "allow"` |
| Same key in deny | `<field>: "ask"` |

MCP servers map directly in both agents — `command` becomes `command`+`args` for Claude; the list form is preserved for Opencode.

## Extension points

- **New agent**: implement `agents/<name>.py:run()`, `agent_setup.build_<name>_config()`, `executor.execute_<name>()`, register in `orchestrator.AGENTS` and CLI `--agent` choices.
- **New discovery source**: add `prompts/sources/<name>.md` and include it in the preset/sources resolution in `prompts/__init__.py`.
- **New validation rule**: extend `validate.validate_bundle()`.

## Security notes

- **Preflight denies** during planning (in `agents/claude.py`, `agents/opencode.py`) block local file access, shell execution, and fetches to `file://`, `localhost`, `127.0.0.1`, and `169.254.169.254` (IMDS).
- **`scrub_env`** strips known credential env vars before invoking the subprocess.
- **Tool allowlist** at execute time means the agent cannot use a tool that wasn't enabled in the reviewed bundle, even if the agent CLI would otherwise have it available.
- **No global config writes.** Settings files live inside the bundle directory.
