from __future__ import annotations


def valid_bundle() -> dict:
    return {
        "task": "demo",
        "skills": [
            {
                "name": "python-skill",
                "source_url": "https://github.com/anthropics/skills",
                "origin": "anthropic",
                "install": "git clone https://github.com/anthropics/skills",
                "rationale": "Python scaffolding.",
            }
        ],
        "tools": [
            {
                "name": "postgres-mcp",
                "kind": "mcp",
                "source_url": "https://github.com/modelcontextprotocol/servers",
                "install": "npx -y @modelcontextprotocol/server-postgres",
                "auth": "PG_URL env",
                "rationale": "DB access.",
            }
        ],
        "permissions": {"allow": ["WebFetch"], "deny": ["Bash(rm:*)"]},
        "plan_markdown": "## Plan\n1. Step",
        "prompt_recommendations": "- Be explicit about schema.",
    }


def malformed_bundle() -> dict:
    b = valid_bundle()
    b["skills"][0]["origin"] = "not-a-real-origin"
    return b
