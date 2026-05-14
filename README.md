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
ultra-plan execute <dir> [flags]
```

### Flags

**`run` command:**

| flag | default | meaning |
| --- | --- | --- |
| `--agent` | `claude` | `claude` or `opencode` |
| `--sources` | (preset) | comma list: `github,mcp,anthropic,web` |
| `--preset` | `wide` | `wide` (all sources) or `local-only` |
| `--out` | `./ultra-plan/<slug>/` | output dir |
| `--port` | `7777` | review-server port |
| `--no-browser` | off | skip auto-open |

**`review` command:**

| flag | default | meaning |
| --- | --- | --- |
| `--port` | `7777` | review-server port |
| `--no-browser` | off | skip auto-open |

**`execute` command:**

| flag | default | meaning |
| --- | --- | --- |
| `--agent` | `claude` | `claude` or `opencode` |
| `--headless` | off | run non-interactively with JSON output |
| `--cwd` | bundle dir | working directory for execution |

## Flow

### Planning Flow (`run`)

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

### Execution Flow (`execute`)

```
ultra-plan execute <dir> [--agent claude|opencode]
   1. Load bundle.json from the specified directory
   2. Extract enabled tools, permissions, and prompt recommendations
   3. Build execution prompt from:
      - prompt_recommendations (instructions)
      - expected_outcome (success criteria)
      - plan_markdown (implementation plan)
      - task (original task description)
   4. Invoke the selected agent CLI with:
      - Allowed tools (--allowedTools for claude)
      - Execution prompt via stdin
      - Optional headless mode for automation
   5. Agent executes the task with configured tools and context
```

## Output

Under `--out`:

```
bundle.json                       # canonical, validated, written immediately
index.html / app.js / style.css   # review UI, copied from package
```

After clicking **Confirm** in the review UI, the server also writes:

```
expected-outcome.md        # task deliverables and success criteria
skills.json                # enabled items only
tools.json                 # enabled items only
permissions.json           # proposed settings.json patch (NOT applied)
plan.md
prompt-recommendations.md
```

No installation is performed — write-only by design.

## Execution

Once you've reviewed and confirmed a bundle, execute it with:

```bash
ultra-plan execute ./ultra-plan/build-a-rest-api/
```

The `execute` command:
- Reads the bundle configuration
- Extracts enabled tools and builds an `--allowedTools` list
- Combines prompt recommendations, expected outcome, plan, and task into an execution prompt
- Launches the selected agent CLI (claude or opencode) with the configured environment
- For Claude: uses `claude -p --allowedTools <list>`
- For opencode: uses `opencode run --`

### Interactive vs Headless

By default, `execute` runs **interactively** — you can see the agent's output and interact with it in real-time.

For automation or scripting, use `--headless`:

```bash
ultra-plan execute ./ultra-plan/build-a-rest-api/ --headless
```

This runs the agent non-interactively and captures JSON output.

### Skills and Permissions

**Skills**: The execute command assumes any required skills are already installed. The bundle's `skills[].install` field documents how to install them — this must be done manually before execution.

**Permissions**: The execute command generates a temporary `settings.json` with the bundle's permissions for reference. For Claude CLI, you may need to manually apply these to your `~/.claude/settings.json` before execution, or approve them interactively during execution.
