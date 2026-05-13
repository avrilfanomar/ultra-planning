"""
Demonstration of improved error messages.

This test shows what users will see when common errors occur.
"""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from ultra_plan.agents import claude


class TestErrorMessageDemo:
    """Demonstrates the improved error messages users will see."""

    def test_api_key_error_message_is_helpful(self):
        """Verify API key errors give clear instructions."""
        # Simulate the actual error from Claude CLI with invalid API key
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = ""
        error.stdout = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "api_error_status": 401,
            "result": "Invalid API key · Fix external API key"
        })

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test task", allowed_tools=["Read", "Write"])

        error_message = str(exc_info.value)

        # Verify the error message is helpful
        print("\n" + "=" * 70)
        print("IMPROVED ERROR MESSAGE:")
        print("=" * 70)
        print(error_message)
        print("=" * 70)

        # Check that it contains helpful information
        assert "Invalid API key" in error_message
        assert "claude auth" in error_message or "ANTHROPIC_API_KEY" in error_message

    def test_rate_limit_error_message_is_clear(self):
        """Verify rate limit errors are clearly communicated."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = ""
        error.stdout = json.dumps({
            "result": "Rate limit exceeded - please try again in 60 seconds"
        })

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_message = str(exc_info.value)

        print("\n" + "=" * 70)
        print("RATE LIMIT ERROR MESSAGE:")
        print("=" * 70)
        print(error_message)
        print("=" * 70)

        assert "Rate limit exceeded" in error_message
        assert "try again later" in error_message

    def test_permission_error_message_suggests_solution(self):
        """Verify permission errors suggest checking API key permissions."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = "403 Forbidden"
        error.stdout = ""

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_message = str(exc_info.value)

        print("\n" + "=" * 70)
        print("PERMISSION ERROR MESSAGE:")
        print("=" * 70)
        print(error_message)
        print("=" * 70)

        assert "Permission denied" in error_message
        assert "API key permissions" in error_message


if __name__ == "__main__":
    # Run with verbose output to see the error messages
    pytest.main([__file__, "-v", "-s"])
