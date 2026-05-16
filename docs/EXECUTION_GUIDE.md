# Execution Guide

How `ultra-plan execute` turns a bundle into a running task. For the planning phase and overall architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Usage

```bash
ultra-plan execute <bundle-dir> [--agent claude|opencode] [--headless] [--cwd <path>]
```

The bundle must already exist (created by `ultra-plan run`). `<bundle-dir>` is the directory containing `bundle.json`.

## What happens

1. **Load** `bundle.json` from `<bundle-dir>`.
2. **Materialize** the agent config into the bundle directory:
   - Claude → `settings.json` (`permissions` block + `mcpServers` block)
   - Opencode → `opencode.json` (coarse `permission` fields + `mcpServers` block)
3. **Build** the execution prompt by concatenating, in order: `# Skills`, `# Instructions` (from `prompt_recommendations`), `# Expected Outcome`, `# Plan` (from `plan_markdown`), `# Task`.
4. **Build** the tool allowlist:
   - `kind: "mcp"` → `mcp__<name>__*` wildcard
   - other kinds → exact name (e.g. `WebSearch`)
   - skip tools with `enabled: false`
5. **Launch** the agent CLI as a subprocess with the prompt, allowlist, and config path.

## Working directory

By default execution runs in the bundle directory, so the agent finds `settings.json`/`opencode.json` automatically and writes artifacts there.

With `--cwd <path>`, the agent runs in `<path>` instead:
- For Claude, `--settings <bundle-dir>/settings.json` is passed explicitly, so the config path doesn't matter.
- For Opencode, `opencode.json` is copied into `<path>` so Opencode's cwd-walking config discovery still finds it.

Use `--cwd` when the bundle lives separately from the codebase you want the agent to modify.

## Interactive vs headless

**Interactive (default)** streams agent output to the terminal. Useful for development; user can interrupt or answer prompts.

**`--headless`** runs the agent non-interactively and emits JSON:

```bash
ultra-plan execute ./ultra-plan/my-task --headless > result.json
```

Translates to `claude --print --output-format json ...` or `opencode run --dangerously-skip-permissions --format json ...`. If the agent expects user input that never comes, the run will hang — make sure the plan and expected outcome leave nothing ambiguous, and validate interactively first.

## Example: Claude config materialization

Bundle input:
```json
{
  "permissions": {"allow": ["Write", "Edit"], "deny": ["Bash(rm:*)"]},
  "tools": [
    {"name": "postgres-mcp", "kind": "mcp", "enabled": true,
     "command": ["npx", "-y", "@modelcontextprotocol/server-postgres"]}
  ]
}
```

Generated `settings.json`:
```json
{
  "permissions": {"allow": ["Write", "Edit"], "deny": ["Bash(rm:*)"]},
  "mcpServers": {
    "postgres-mcp": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"]
    }
  }
}
```

Allowlist passed to Claude: `--allowedTools mcp__postgres-mcp__*`.

## Iterating on a bundle

The bundle is the source of truth — edit `bundle.json` and re-run `execute`. The materialized config is regenerated each time.

```bash
# Tighten permissions, then re-run
$EDITOR ./ultra-plan/my-task/bundle.json
ultra-plan execute ./ultra-plan/my-task
```

## Troubleshooting

**`No bundle.json found at <dir>`** — run `ultra-plan run "<task>"` first.

**`claude CLI not found on PATH`** — install the agent CLI (Claude Code, or `pip install opencode-ai`).

**Permission denied during execution** — the tool wasn't enabled in the bundle, or the permission isn't in `permissions.allow`. Inspect with:
```bash
jq '.permissions, .tools' ./ultra-plan/my-task/bundle.json
cat ./ultra-plan/my-task/settings.json
```
Then edit `bundle.json` and re-execute.

**MCP server fails to start** — test the command directly (e.g. `npx -y @modelcontextprotocol/server-filesystem /tmp`) to surface the real error. Ensure Node.js is installed for `npx`-based servers.

**Headless run hangs** — the agent is waiting for input it can't get. Make the plan and expected outcome unambiguous, or debug interactively.

**Artifacts written to the wrong place** — the agent ran in the bundle directory by default; pass `--cwd <project-dir>` to redirect, or `cd` there and pass an absolute bundle path.

**Opencode warns about missing `opencode.json`** — you used `--cwd` and the config copy didn't land. Check that `<cwd>/opencode.json` exists; otherwise omit `--cwd` and run from the bundle directory.
