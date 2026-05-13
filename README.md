# ultra-plan

A CLI that produces a **fixed, reviewable bundle** of skills, tools, MCP servers, permission patches, and prompt recommendations for a task — by delegating the discovery loop to a headless coding agent (Claude Code by default; opencode also supported).

## Install

```
pip install -e .
```

Requires Python 3.10+. The `claude` CLI (or `opencode`) must be on `$PATH` for live runs.

## Usage

```
ultra-plan "<task>" [flags]
ultra-plan run "<task>" [flags]
ultra-plan review <dir>
```

### Flags

| flag | default | meaning |
| --- | --- | --- |
| `--agent` | `claude` | `claude` or `opencode` |
| `--sources` | (preset) | comma list: `github,mcp,anthropic,web` |
| `--preset` | `wide` | `wide` (all sources) or `local-only` |
| `--out` | `./ultra-plan/<slug>/` | output dir |
| `--port` | `7777` | review-server port |
| `--no-browser` | off | skip auto-open |

## Flow

```
ultra-plan CLI (thin orchestrator)
   1. Parse task + flags
   2. Render prompt template for the chosen agent
   3. Invoke `claude -p` or `opencode run` headless
      with task + source list + output schema
   4. Agent uses WebSearch/WebFetch + source adapters
      to discover matches, ranks them, writes raw bundle
   5. CLI validates the bundle against JSON schemas
   6. CLI starts local review server, opens browser
   7. On confirm: persist final bundle to --out
```

## Output

Under `--out`:

```
bundle.json                       # canonical, validated, written immediately
index.html / app.js / style.css   # review UI, copied from package
```

After clicking **Confirm** in the review UI, the server also writes:

```
skills.json                # enabled items only
tools.json                 # enabled items only
permissions.json           # proposed settings.json patch (NOT applied)
plan.md
prompt-recommendations.md
```

No installation is performed — write-only by design.
