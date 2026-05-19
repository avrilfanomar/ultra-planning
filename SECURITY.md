# Security Policy

## Supported Versions

Security fixes are applied to the latest minor release line. Older lines are
end-of-life and receive no fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Threat model — what is in scope

`ultra-plan` runs against attacker-controlled web content (search results,
fetched pages, MCP registries) during its planning preflight. The following
are explicit in-scope concerns:

- Prompt injection via web sources causing the planner to emit malicious tool
  permissions, MCP commands, or skills.
- Escape from the preflight sandbox (which denies file/shell tools via static
  policy and scrubs the subprocess environment).
- Cross-site request forgery against the local review server.
- Sandbox escape via the `execute` working directory.
- Local DoS against the review HTTP server.

## Out of scope

- Vulnerabilities in the `claude` or `opencode` upstream CLIs — report those
  to their respective vendors.
- Misconfiguration by an operator who explicitly opts out of safeguards
  (e.g. passing `--allow-external-cwd`, `--pass-env`, or disabling timeouts).
- Issues that require a privileged local attacker on the same machine.
