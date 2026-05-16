"""Tests for ultra_plan.agents._env.scrub_env.

Verifies the env scrubbing applied to preflight and execute subprocess
invocations actually drops secret-shaped variables and preserves the
allowed names / prefixes declared in the module.
"""
from __future__ import annotations

from ultra_plan.agents._env import scrub_env


def test_secret_shaped_vars_dropped():
    """AWS, GitHub, and provider-API-key vars must not leak into the sandbox."""
    env = {
        "AWS_ACCESS_KEY_ID": "AKIA-fake",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "GITHUB_TOKEN": "ghp_fake",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
        "OPENAI_API_KEY": "sk-openai-fake",
        # Allowlisted entries that must survive:
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "LANG": "en_US.UTF-8",
    }

    scrubbed = scrub_env(env)

    assert "AWS_ACCESS_KEY_ID" not in scrubbed
    assert "AWS_SECRET_ACCESS_KEY" not in scrubbed
    assert "GITHUB_TOKEN" not in scrubbed
    assert "ANTHROPIC_API_KEY" not in scrubbed
    assert "OPENAI_API_KEY" not in scrubbed

    assert scrubbed["PATH"] == "/usr/bin"
    assert scrubbed["HOME"] == "/home/user"
    assert scrubbed["LANG"] == "en_US.UTF-8"


def test_allowlisted_exact_keys_preserved():
    """Each exact-match name in ALLOWED_ENV_KEYS is preserved."""
    env = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LANG": "C",
    }
    scrubbed = scrub_env(env)
    assert scrubbed == env


def test_allowlisted_prefixes_pass_through():
    """Variables matching CLAUDE_/OPENCODE_/LC_/XDG_ prefixes are kept."""
    env = {
        "CLAUDE_CODE_FOO": "1",
        "OPENCODE_BAR": "2",
        "LC_ALL": "C.UTF-8",
        "XDG_RUNTIME_DIR": "/run/user/1000",
    }
    scrubbed = scrub_env(env)
    assert scrubbed["CLAUDE_CODE_FOO"] == "1"
    assert scrubbed["OPENCODE_BAR"] == "2"
    assert scrubbed["LC_ALL"] == "C.UTF-8"
    assert scrubbed["XDG_RUNTIME_DIR"] == "/run/user/1000"


def test_unknown_var_dropped():
    """Vars not in the allowlist and not matching a prefix are dropped."""
    env = {"FOO": "bar", "PATH": "/usr/bin"}
    scrubbed = scrub_env(env)
    assert "FOO" not in scrubbed
    assert scrubbed["PATH"] == "/usr/bin"


def test_combined_realistic_env():
    """End-to-end check mixing secrets, allowlisted, prefixed, and unknown vars."""
    env = {
        "AWS_ACCESS_KEY_ID": "secret",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "GITHUB_TOKEN": "secret",
        "ANTHROPIC_API_KEY": "secret",
        "OPENAI_API_KEY": "secret",
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LANG": "C",
        "CLAUDE_CODE_FOO": "1",
        "OPENCODE_BAR": "2",
        "LC_ALL": "C.UTF-8",
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "FOO": "bar",
    }
    scrubbed = scrub_env(env)
    for secret_key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "FOO",
    ):
        assert secret_key not in scrubbed, secret_key
    for kept_key in (
        "PATH",
        "HOME",
        "LANG",
        "CLAUDE_CODE_FOO",
        "OPENCODE_BAR",
        "LC_ALL",
        "XDG_RUNTIME_DIR",
    ):
        assert kept_key in scrubbed, kept_key
