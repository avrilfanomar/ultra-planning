from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ultra_plan.agents import claude, opencode
from ultra_plan.agents._env import scrub_env
from ultra_plan import orchestrator


_BUNDLE_STDOUT = """===BUNDLE-BEGIN===
{"skills":[],"tools":[],"permissions":{"allow":[],"deny":[]},"plan_markdown":"x","prompt_recommendations":"x"}
===BUNDLE-END==="""


def _mock_proc(stdout: str = _BUNDLE_STDOUT) -> Mock:
    m = Mock()
    m.stdout = stdout
    m.returncode = 0
    return m


class TestDefaultAllowedTools:
    def test_planning_run_minimum_toolset(self):
        assert orchestrator.DEFAULT_ALLOWED_TOOLS == ["WebSearch", "WebFetch"]


class TestEnvScrub:
    def test_drops_secrets(self):
        env = {
            "AWS_SECRET_ACCESS_KEY": "x",
            "GITHUB_TOKEN": "y",
            "OPENAI_API_KEY": "z",
            "ANTHROPIC_API_KEY": "a",
            "PATH": "/usr/bin",
        }
        out = scrub_env(env)
        assert out == {"PATH": "/usr/bin"}

    def test_keeps_essentials_and_prefixed(self):
        env = {
            "HOME": "/home/u",
            "PATH": "/usr/bin",
            "CLAUDE_FOO": "bar",
            "OPENCODE_BAR": "baz",
            "LC_ALL": "C",
            "XDG_CONFIG_HOME": "/tmp/x",
            "TZ": "UTC",
            "RANDOM_TOKEN": "leak",
        }
        out = scrub_env(env)
        assert "RANDOM_TOKEN" not in out
        for k in ("HOME", "PATH", "CLAUDE_FOO", "OPENCODE_BAR", "LC_ALL", "XDG_CONFIG_HOME", "TZ"):
            assert k in out


class TestClaudePreflight:
    def test_settings_materialized_and_cwd_sandboxed(self):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs["cwd"]
            captured["env"] = kwargs["env"]
            settings_idx = cmd.index("--settings")
            settings_path = Path(cmd[settings_idx + 1])
            captured["settings"] = json.loads(settings_path.read_text())
            captured["settings_parent"] = settings_path.parent
            return _mock_proc()

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict("os.environ", {"GITHUB_TOKEN": "leak", "PATH": "/usr/bin", "HOME": "/h"}, clear=True):
                claude.run("p", allowed_tools=["WebSearch", "WebFetch"])

        # cwd == directory containing settings.json (sandboxed temp dir)
        assert captured["cwd"] == captured["settings_parent"]
        # env scrubbed
        assert "GITHUB_TOKEN" not in captured["env"]
        assert captured["env"]["PATH"] == "/usr/bin"
        # deny list contains the dangerous primitives
        deny = captured["settings"]["permissions"]["deny"]
        for entry in ("Read", "Write", "Bash"):
            assert entry in deny
        # SSRF guards present
        assert any("169.254.169.254" in e for e in deny)
        assert any("localhost" in e for e in deny)


class TestOpencodePreflight:
    def test_no_dangerously_skip_permissions_and_config_materialized(self):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs["cwd"]
            captured["env"] = kwargs["env"]
            cfg_path = Path(kwargs["cwd"]) / "opencode.json"
            captured["config"] = json.loads(cfg_path.read_text())
            return _mock_proc()

        with patch("subprocess.run", side_effect=fake_run):
            with patch.dict("os.environ", {"AWS_SECRET_ACCESS_KEY": "x", "PATH": "/usr/bin"}, clear=True):
                opencode.run("p", allowed_tools=["WebSearch"])

        assert "--dangerously-skip-permissions" not in captured["cmd"]
        assert "AWS_SECRET_ACCESS_KEY" not in captured["env"]
        perm = captured["config"]["permission"]
        assert perm["read"] == "deny"
        assert perm["write"] == "deny"
        assert perm["edit"] == "deny"
        assert perm["bash"] == "deny"
        assert perm["external_directory"] == "deny"
        assert perm["webfetch"] == "allow"

    def test_file_not_found_raises_clear_error(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="opencode CLI not found"):
                opencode.run("p", allowed_tools=[])
