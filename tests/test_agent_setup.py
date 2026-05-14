from __future__ import annotations

import pytest

from ultra_plan.agent_setup import (
    build_claude_settings,
    build_opencode_config,
    build_skills_context,
)
from tests.fixtures import valid_bundle


# ---------------------------------------------------------------------------
# build_claude_settings
# ---------------------------------------------------------------------------

class TestBuildClaudeSettings:
    def test_permissions_present(self):
        bundle = valid_bundle()
        result = build_claude_settings(bundle)
        assert "permissions" in result
        assert result["permissions"]["allow"] == bundle["permissions"]["allow"]
        assert result["permissions"]["deny"] == bundle["permissions"]["deny"]

    def test_mcp_without_transport_skipped(self):
        """The default fixture MCP tool has no command/url — should be omitted."""
        bundle = valid_bundle()
        result = build_claude_settings(bundle)
        assert "mcpServers" not in result

    def test_mcp_with_command_included(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = "npx"
        result = build_claude_settings(bundle)
        assert "mcpServers" in result
        assert "postgres-mcp" in result["mcpServers"]
        assert result["mcpServers"]["postgres-mcp"]["command"] == "npx"

    def test_mcp_with_command_list(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = ["npx", "-y", "@mcp/server"]
        result = build_claude_settings(bundle)
        entry = result["mcpServers"]["postgres-mcp"]
        assert entry["command"] == "npx"
        assert entry["args"] == ["-y", "@mcp/server"]

    def test_mcp_with_url_included(self):
        bundle = valid_bundle()
        bundle["tools"][0]["url"] = "https://mcp.example.com"
        result = build_claude_settings(bundle)
        assert result["mcpServers"]["postgres-mcp"]["url"] == "https://mcp.example.com"

    def test_disabled_mcp_tool_skipped(self):
        bundle = valid_bundle()
        bundle["tools"][0]["enabled"] = False
        bundle["tools"][0]["command"] = "npx"
        result = build_claude_settings(bundle)
        assert "mcpServers" not in result

    def test_empty_permissions_not_in_result(self):
        bundle = {"task": "x"}
        result = build_claude_settings(bundle)
        assert result == {}

    def test_only_allow_key_present(self):
        bundle = {"task": "x", "permissions": {"allow": ["WebFetch"]}}
        result = build_claude_settings(bundle)
        assert result["permissions"]["allow"] == ["WebFetch"]
        assert "deny" not in result["permissions"]
        assert "ask" not in result["permissions"]

    def test_ask_key_forwarded(self):
        bundle = {"task": "x", "permissions": {"ask": ["Bash(*)", "Write"]}}
        result = build_claude_settings(bundle)
        assert result["permissions"]["ask"] == ["Bash(*)", "Write"]


# ---------------------------------------------------------------------------
# build_opencode_config
# ---------------------------------------------------------------------------

class TestBuildOpencodeConfig:
    def test_schema_always_present(self):
        result = build_opencode_config({})
        assert result["$schema"] == "https://opencode.ai/config.json"

    def test_allow_write_maps_to_permission_write(self):
        bundle = {"permissions": {"allow": ["Write"]}}
        result = build_opencode_config(bundle)
        assert result["permission"]["write"] == "allow"

    def test_allow_edit_maps_to_permission_edit(self):
        bundle = {"permissions": {"allow": ["Edit"]}}
        result = build_opencode_config(bundle)
        assert result["permission"]["edit"] == "allow"

    def test_allow_bash_maps_to_permission_bash(self):
        bundle = {"permissions": {"allow": ["Bash(git:*)"]}}
        result = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "allow"

    def test_deny_overrides_allow(self):
        bundle = {"permissions": {"allow": ["Bash(git:*)"], "deny": ["Bash(rm:*)"]}}
        result = build_opencode_config(bundle)
        # deny takes precedence
        assert result["permission"]["bash"] == "ask"

    def test_deny_without_allow_still_produces_ask(self):
        """A deny entry with no matching allow still emits 'ask'."""
        bundle = {"permissions": {"deny": ["Bash(rm:*)"]}}
        result = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "ask"

    def test_valid_bundle_permissions(self):
        bundle = valid_bundle()
        # allow: ["WebFetch"], deny: ["Bash(rm:*)"]
        result = build_opencode_config(bundle)
        # WebFetch doesn't match write/edit/bash → no write/edit key
        assert "write" not in result.get("permission", {})
        assert "edit" not in result.get("permission", {})
        # Bash(rm:*) is in deny → bash: "ask"
        assert result["permission"]["bash"] == "ask"

    def test_mcp_without_transport_skipped(self):
        bundle = valid_bundle()
        result = build_opencode_config(bundle)
        assert "mcp" not in result

    def test_mcp_with_command_list(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = ["npx", "-y", "@mcp/server"]
        result = build_opencode_config(bundle)
        entry = result["mcp"]["postgres-mcp"]
        assert entry["type"] == "local"
        assert entry["command"] == ["npx", "-y", "@mcp/server"]
        assert entry["enabled"] is True

    def test_mcp_with_command_string_normalized_to_list(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = "npx"
        result = build_opencode_config(bundle)
        assert result["mcp"]["postgres-mcp"]["command"] == ["npx"]

    def test_mcp_with_url(self):
        bundle = valid_bundle()
        bundle["tools"][0]["url"] = "https://mcp.example.com"
        result = build_opencode_config(bundle)
        entry = result["mcp"]["postgres-mcp"]
        assert entry["type"] == "remote"
        assert entry["url"] == "https://mcp.example.com"

    def test_disabled_mcp_skipped(self):
        bundle = valid_bundle()
        bundle["tools"][0]["enabled"] = False
        bundle["tools"][0]["command"] = "npx"
        result = build_opencode_config(bundle)
        assert "mcp" not in result

    def test_empty_bundle_only_schema(self):
        result = build_opencode_config({})
        assert list(result.keys()) == ["$schema"]


# ---------------------------------------------------------------------------
# build_skills_context
# ---------------------------------------------------------------------------

class TestBuildSkillsContext:
    def test_enabled_skill_included(self):
        bundle = valid_bundle()
        result = build_skills_context(bundle)
        assert "# Skills" in result
        assert "python-skill" in result
        assert "https://github.com/anthropics/skills" in result
        assert "Python scaffolding." in result

    def test_disabled_skill_excluded(self):
        bundle = valid_bundle()
        bundle["skills"][0]["enabled"] = False
        result = build_skills_context(bundle)
        assert result == ""

    def test_no_skills_returns_empty_string(self):
        bundle = {"task": "x"}
        result = build_skills_context(bundle)
        assert result == ""

    def test_empty_skills_list_returns_empty_string(self):
        bundle = {"task": "x", "skills": []}
        result = build_skills_context(bundle)
        assert result == ""

    def test_multiple_skills_one_disabled(self):
        bundle = {
            "skills": [
                {
                    "name": "skill-a",
                    "source_url": "https://example.com/a",
                    "rationale": "Rationale A",
                    "enabled": True,
                },
                {
                    "name": "skill-b",
                    "source_url": "https://example.com/b",
                    "rationale": "Rationale B",
                    "enabled": False,
                },
            ]
        }
        result = build_skills_context(bundle)
        assert "skill-a" in result
        assert "skill-b" not in result

    def test_bullet_format(self):
        bundle = {
            "skills": [
                {
                    "name": "my-skill",
                    "source_url": "https://example.com/skill",
                    "rationale": "Useful.",
                }
            ]
        }
        result = build_skills_context(bundle)
        assert "- **my-skill** (https://example.com/skill): Useful." in result
