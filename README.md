# ultra-plan

ultra-plan is a CLI that produces a reviewable bundle of skills, tools, MCP
servers, and permission patches for a task by delegating discovery to
a headless agent (Claude Code by default; opencode also supported). The
bundle is written to disk; nothing is installed.

## WHAT IS IN A BUNDLE

A bundle is a directory under `--out` (default `./ultra-plan/<slug>/`)
containing:

    bundle.json                 canonical, validated bundle
    preflight-settings.json     permissions used during planning (claude)
    preflight-config.json       permissions used during planning (opencode)
    index.html, app.js, style.css   review UI (served locally)

After you click Confirm in the review UI, the server also writes:

    expected-outcome.md         deliverables and success criteria
    skills.json                 enabled skills only
    tools.json                  enabled tools only
    permissions.json            proposed settings.json patch
    plan.md                     implementation plan
    prompt-recommendations.md   instructions for the executing agent

When `execute` runs, the directory also gains `settings.json` (Claude) or
`opencode.json` (opencode), materialized from the bundle's permissions and
MCP configuration.

## INSTALLING

    pip install -e .

Requires Python 3.10+. The `claude` CLI (or `opencode`) must be on `$PATH`
for live runs.

## USING IT

    ultra-plan "<task>" [flags]
    ultra-plan run "<task>" [flags]
    ultra-plan review <dir>
    ultra-plan execute <dir> [flags]

`run` plans a task: it invokes the agent headless, validates the resulting
bundle against JSON schemas, starts a local review server, and opens a
browser. On confirm the final bundle is persisted to `--out`.

`review` re-opens the review UI for an existing bundle directory.

`execute` reads `bundle.json`, materializes agent config into the bundle
directory, builds an execution prompt from the plan, prompt recommendations,
expected outcome, and original task, and launches the configured agent. By
default execute is interactive; `--headless` runs non-interactively with
JSON output.

For the full flag list run `ultra-plan <command> --help`.

## SECURITY

The planning agent runs against attacker-controlled web content (search
results, fetched pages, MCP registries), so the preflight run is hardened
against prompt injection:

  - The agent subprocess inherits only a small allowlist of environment
    variables; tokens, API keys, and `AWS_*`/`GITHUB_*` secrets are dropped.
  - The materialized `settings.json` denies `Read`, `Write`, `Edit`,
    `NotebookEdit`, and `Bash` regardless of any `--allowedTools` passed in.
  - `WebFetch` denies `file://`, `http://localhost`, `http://127.0.0.1`,
    and `http://169.254.169.254` (cloud metadata).
  - Prompts are piped via stdin, so leading `-` cannot be parsed as a flag.
  - The agent runs in a fresh temp `cwd` containing only `settings.json`.
  - The preflight permissions are persisted to the bundle directory as
    `preflight-settings.json` (claude) or `preflight-config.json` (opencode)
    for transparency and audit purposes.

These protections apply to `run` only. `execute` runs with the tools and
permissions you confirmed in the review UI — review them before executing.

See `src/ultra_plan/agents/_env.py` for the environment allowlist.
