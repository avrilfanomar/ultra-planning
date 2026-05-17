from __future__ import annotations

from tests.fixtures import valid_bundle
from ultra_plan.agent_setup import (
    build_claude_settings,
    build_opencode_config,
    build_skills_context,
)

# ---------------------------------------------------------------------------
# build_claude_settings
# ---------------------------------------------------------------------------

class TestBuildClaudeSettings:
    def test_permissions_present(self):
        bundle = valid_bundle()
        result, _skipped = build_claude_settings(bundle)
        assert "permissions" in result
        assert result["permissions"]["allow"] == bundle["permissions"]["allow"]
        assert result["permissions"]["deny"] == bundle["permissions"]["deny"]

    def test_mcp_without_transport_skipped(self):
        """The default fixture MCP tool has no command/url — should be omitted and surfaced."""
        bundle = valid_bundle()
        result, skipped = build_claude_settings(bundle)
        assert "mcpServers" not in result
        # The fixture's MCP tool name should appear in the skipped list.
        assert "postgres-mcp" in skipped

    def test_mcp_with_command_included(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = "npx"
        result, skipped = build_claude_settings(bundle)
        assert "mcpServers" in result
        assert "postgres-mcp" in result["mcpServers"]
        assert result["mcpServers"]["postgres-mcp"]["command"] == "npx"
        assert skipped == []

    def test_mcp_with_command_list(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = ["npx", "-y", "@mcp/server"]
        result, _skipped = build_claude_settings(bundle)
        entry = result["mcpServers"]["postgres-mcp"]
        assert entry["command"] == "npx"
        assert entry["args"] == ["-y", "@mcp/server"]

    def test_mcp_with_url_included(self):
        bundle = valid_bundle()
        bundle["tools"][0]["url"] = "https://mcp.example.com"
        result, skipped = build_claude_settings(bundle)
        assert result["mcpServers"]["postgres-mcp"]["url"] == "https://mcp.example.com"
        assert skipped == []

    def test_disabled_mcp_tool_skipped(self):
        bundle = valid_bundle()
        bundle["tools"][0]["enabled"] = False
        bundle["tools"][0]["command"] = "npx"
        result, skipped = build_claude_settings(bundle)
        assert "mcpServers" not in result
        # Disabled tools must NOT appear in the skipped (warning) list.
        assert skipped == []

    def test_empty_permissions_not_in_result(self):
        bundle = {"task": "x"}
        result, skipped = build_claude_settings(bundle)
        assert result == {}
        assert skipped == []

    def test_only_allow_key_present(self):
        bundle = {"task": "x", "permissions": {"allow": ["WebFetch"]}}
        result, _skipped = build_claude_settings(bundle)
        assert result["permissions"]["allow"] == ["WebFetch"]
        assert "deny" not in result["permissions"]
        assert "ask" not in result["permissions"]

    def test_ask_key_forwarded(self):
        bundle = {"task": "x", "permissions": {"ask": ["Bash(*)", "Write"]}}
        result, _skipped = build_claude_settings(bundle)
        assert result["permissions"]["ask"] == ["Bash(*)", "Write"]


# ---------------------------------------------------------------------------
# build_opencode_config
# ---------------------------------------------------------------------------
#
# The permission-mapping tests below lock in *current* behaviour, including
# the deny-widens-to-ask semantics flagged in the improvement plan: when a
# deny entry matches one of the broad keys (write/edit/bash), the resulting
# value is "ask" rather than "deny" — even when the same key was previously
# resolved to "allow" via an allow entry. This is intentional documentation
# of present behaviour, not an endorsement of it.

class TestBuildOpencodeConfig:
    def test_schema_always_present(self):
        result, _skipped = build_opencode_config({})
        assert result["$schema"] == "https://opencode.ai/config.json"

    def test_allow_write_maps_to_permission_write(self):
        bundle = {"permissions": {"allow": ["Write"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["write"] == "allow"

    def test_allow_edit_maps_to_permission_edit(self):
        bundle = {"permissions": {"allow": ["Edit"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["edit"] == "allow"

    def test_allow_bash_maps_to_permission_bash(self):
        bundle = {"permissions": {"allow": ["Bash(git:*)"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "allow"

    def test_deny_overrides_allow(self):
        bundle = {"permissions": {"allow": ["Bash(git:*)"], "deny": ["Bash(rm:*)"]}}
        result, _skipped = build_opencode_config(bundle)
        # deny takes precedence
        assert result["permission"]["bash"] == "ask"

    def test_deny_without_allow_still_produces_ask(self):
        """A deny entry with no matching allow still emits 'ask'."""
        bundle = {"permissions": {"deny": ["Bash(rm:*)"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "ask"

    # --- Permission mapping edge cases (locking in current semantics) ---

    def test_allow_bash_prefix_form(self):
        """`Bash(ls)` (prefix form) maps to allow — the parameterized variant."""
        bundle = {"permissions": {"allow": ["Bash(ls)"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "allow"

    def test_deny_bash_rm_with_allow_bash_ls_widens_to_ask(self):
        """deny `Bash(rm -rf /)` while allow has `Bash(ls)` -> bash == "ask"."""
        bundle = {
            "permissions": {
                "allow": ["Bash(ls)"],
                "deny": ["Bash(rm -rf /)"],
            }
        }
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "ask"

    def test_deny_bare_bash_no_allow_is_ask(self):
        """deny `Bash` (no allow entry) -> bash == "ask"."""
        bundle = {"permissions": {"deny": ["Bash"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["bash"] == "ask"

    def test_allow_write_and_edit_both_map(self):
        """allow `Write` and `Edit` -> both write and edit map to "allow"."""
        bundle = {"permissions": {"allow": ["Write", "Edit"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["write"] == "allow"
        assert result["permission"]["edit"] == "allow"

    def test_deny_edit_no_matching_allow_is_ask(self):
        """deny `Edit` with no allow entry -> edit == "ask"."""
        bundle = {"permissions": {"deny": ["Edit"]}}
        result, _skipped = build_opencode_config(bundle)
        assert result["permission"]["edit"] == "ask"

    # --- end edge cases ---

    def test_valid_bundle_permissions(self):
        bundle = valid_bundle()
        # allow: ["WebFetch"], deny: ["Bash(rm:*)"]
        result, _skipped = build_opencode_config(bundle)
        # WebFetch doesn't match write/edit/bash → no write/edit key
        assert "write" not in result.get("permission", {})
        assert "edit" not in result.get("permission", {})
        # Bash(rm:*) is in deny → bash: "ask"
        assert result["permission"]["bash"] == "ask"

    def test_mcp_without_transport_skipped(self):
        bundle = valid_bundle()
        result, skipped = build_opencode_config(bundle)
        assert "mcp" not in result
        assert "postgres-mcp" in skipped

    def test_mcp_with_command_list(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = ["npx", "-y", "@mcp/server"]
        result, _skipped = build_opencode_config(bundle)
        entry = result["mcp"]["postgres-mcp"]
        assert entry["type"] == "local"
        assert entry["command"] == ["npx", "-y", "@mcp/server"]
        assert entry["enabled"] is True

    def test_mcp_with_command_string_normalized_to_list(self):
        bundle = valid_bundle()
        bundle["tools"][0]["command"] = "npx"
        result, _skipped = build_opencode_config(bundle)
        assert result["mcp"]["postgres-mcp"]["command"] == ["npx"]

    def test_mcp_with_url(self):
        bundle = valid_bundle()
        bundle["tools"][0]["url"] = "https://mcp.example.com"
        result, _skipped = build_opencode_config(bundle)
        entry = result["mcp"]["postgres-mcp"]
        assert entry["type"] == "remote"
        assert entry["url"] == "https://mcp.example.com"

    def test_disabled_mcp_skipped(self):
        bundle = valid_bundle()
        bundle["tools"][0]["enabled"] = False
        bundle["tools"][0]["command"] = "npx"
        result, skipped = build_opencode_config(bundle)
        assert "mcp" not in result
        assert skipped == []

    def test_empty_bundle_only_schema(self):
        result, _skipped = build_opencode_config({})
        assert list(result.keys()) == ["$schema"]


# ---------------------------------------------------------------------------
# build_skills_context
# ---------------------------------------------------------------------------

class TestBuildSkillsContext:
    def test_enabled_skill_included(self):
        bundle = valid_bundle()
        result, missing = build_skills_context(bundle)
        assert "# Skills" in result
        assert "python-skill" in result
        assert "https://github.com/anthropics/skills" in result
        assert "Python scaffolding." in result
        # No bundle_dir provided → content can't resolve, skill is missing.
        assert missing == ["python-skill"]

    def test_disabled_skill_excluded(self):
        bundle = valid_bundle()
        bundle["skills"][0]["enabled"] = False
        result, missing = build_skills_context(bundle)
        assert result == ""
        assert missing == []

    def test_no_skills_returns_empty_string(self):
        bundle = {"task": "x"}
        result, missing = build_skills_context(bundle)
        assert result == ""
        assert missing == []

    def test_empty_skills_list_returns_empty_string(self):
        bundle = {"task": "x", "skills": []}
        result, missing = build_skills_context(bundle)
        assert result == ""
        assert missing == []

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
        result, missing = build_skills_context(bundle)
        assert "skill-a" in result
        assert "skill-b" not in result
        assert missing == ["skill-a"]

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
        result, missing = build_skills_context(bundle)
        assert "- **my-skill** (https://example.com/skill): Useful." in result
        assert missing == ["my-skill"]

    def test_inlines_skill_md_when_present(self, tmp_path):
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# My Skill\n\nDo the thing.")
        bundle = {
            "skills": [
                {
                    "name": "my-skill",
                    "source_url": "https://example.com/s",
                    "rationale": "R",
                }
            ]
        }
        result, missing = build_skills_context(bundle, tmp_path)
        assert missing == []
        assert "## my-skill" in result
        assert "Do the thing." in result
        # Bullet fallback must not appear when content was inlined.
        assert "- **my-skill**" not in result

    def test_inlines_sibling_md_files(self, tmp_path):
        skill_dir = tmp_path / "skills" / "multi"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("primary body")
        (skill_dir / "extra.md").write_text("extra body")
        bundle = {
            "skills": [
                {"name": "multi", "source_url": "u", "rationale": "r"}
            ]
        }
        result, missing = build_skills_context(bundle, tmp_path)
        assert missing == []
        assert "primary body" in result
        assert "extra body" in result

    def test_falls_back_when_dir_missing(self, tmp_path):
        bundle = {
            "skills": [
                {"name": "absent", "source_url": "u", "rationale": "r"}
            ]
        }
        result, missing = build_skills_context(bundle, tmp_path)
        assert missing == ["absent"]
        assert "- **absent**" in result
        assert "skill content not found" in result
