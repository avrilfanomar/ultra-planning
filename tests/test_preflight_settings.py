"""Tests that the preflight agents carry the documented deny lists.

These lock in the static, defense-in-depth config that wraps the planning
phase. A regression here would silently re-enable Read/Write/Edit/Bash for
the planning agent or open SSRF paths via WebFetch.
"""
from __future__ import annotations

from ultra_plan.agents.claude import _PREFLIGHT_SETTINGS
from ultra_plan.agents.opencode import _PREFLIGHT_CONFIG


class TestClaudePreflightSettings:
    def test_permissions_deny_block_present(self):
        deny = _PREFLIGHT_SETTINGS.get("permissions", {}).get("deny", [])
        for entry in (
            "Read",
            "Write",
            "Edit",
            "NotebookEdit",
            "Bash",
            "WebFetch(file://*)",
            "WebFetch(http://localhost*)",
            "WebFetch(http://127.0.0.1*)",
            "WebFetch(http://169.254.169.254*)",
        ):
            assert entry in deny, f"{entry!r} missing from preflight deny list"


class TestOpencodePreflightConfig:
    def test_permission_block(self):
        perm = _PREFLIGHT_CONFIG.get("permission", {})
        assert perm.get("read") == "deny"
        assert perm.get("edit") == "deny"
        assert perm.get("write") == "deny"
        assert perm.get("bash") == "deny"
        assert perm.get("external_directory") == "deny"
        assert perm.get("webfetch") == "allow"
        assert perm.get("websearch") == "allow"
