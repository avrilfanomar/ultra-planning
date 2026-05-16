from __future__ import annotations

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from ultra_plan.agents import claude


class TestClaudeAgent:
    """Tests for the claude agent module."""

    def test_run_success_with_json_envelope(self):
        """Test successful run with JSON envelope response."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({
            "result": """===BUNDLE-BEGIN===
```json
{
  "skills": [],
  "tools": [],
  "permissions": {"allow": [], "deny": []},
  "plan_markdown": "test",
  "prompt_recommendations": "test"
}
```
===BUNDLE-END==="""
        })
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = claude.run("test prompt", allowed_tools=["Read", "Write"])

        assert result["plan_markdown"] == "test"
        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[:4] == ["claude", "-p", "--output-format", "json"]
        # --settings <path> and --allowedTools <list> must both be present
        assert "--settings" in cmd
        settings_idx = cmd.index("--settings")
        assert cmd[settings_idx + 1].endswith("settings.json")
        tools_idx = cmd.index("--allowedTools")
        assert cmd[tools_idx + 1] == "Read,Write"
        assert args[1]["input"] == "test prompt"
        assert args[1]["check"] is True
        # cwd must be sandboxed (matches the temp dir holding settings.json)
        assert args[1]["cwd"] is not None

    def test_run_success_with_direct_json(self):
        """Test successful run with direct JSON in stdout."""
        mock_result = Mock()
        mock_result.stdout = """===BUNDLE-BEGIN===
```json
{
  "skills": [],
  "tools": [],
  "permissions": {"allow": [], "deny": []},
  "plan_markdown": "direct",
  "prompt_recommendations": "direct"
}
```
===BUNDLE-END==="""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = claude.run("test prompt", allowed_tools=["Read"])

        assert result["plan_markdown"] == "direct"

    def test_run_file_not_found_error(self):
        """Test error when claude CLI is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError("claude not found")):
            with pytest.raises(RuntimeError, match="claude CLI not found on PATH"):
                claude.run("test", allowed_tools=["Read"])

    def test_run_called_process_error_with_api_key_issue(self):
        """Test error handling when Claude CLI returns auth error."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = ""
        error.stdout = json.dumps({
            "result": "Invalid API key · Fix external API key"
        })

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_msg = str(exc_info.value)
        assert "Invalid API key" in error_msg
        assert "ANTHROPIC_API_KEY" in error_msg or "claude auth" in error_msg

    def test_run_called_process_error_generic(self):
        """Test error handling for generic subprocess failures."""
        error = subprocess.CalledProcessError(127, ["claude"])
        error.stderr = "command not found: claude"

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        assert "claude CLI failed with exit code 127" in str(exc_info.value)
        assert "command not found" in str(exc_info.value)

    def test_run_truncates_long_stderr(self):
        """Test that long stderr messages are truncated."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = "x" * 1000  # Long error message

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_message = str(exc_info.value)
        # Should only include last 500 chars
        assert len(error_message) < 600
        assert "x" * 100 in error_message

    def test_extract_assistant_text_from_result_key(self):
        """Test extraction of assistant text from 'result' key."""
        envelope = {"result": "Test response"}
        assert claude._extract_assistant_text(envelope) == "Test response"

    def test_extract_assistant_text_from_response_key(self):
        """Test extraction of assistant text from 'response' key."""
        envelope = {"response": "Test response"}
        assert claude._extract_assistant_text(envelope) == "Test response"

    def test_extract_assistant_text_from_messages_array(self):
        """Test extraction from messages array with content strings."""
        envelope = {
            "messages": [
                {"content": "First message"},
                {"content": "Second message"},
            ]
        }
        result = claude._extract_assistant_text(envelope)
        assert result == "First message\nSecond message"

    def test_extract_assistant_text_from_messages_with_parts(self):
        """Test extraction from messages with content parts."""
        envelope = {
            "messages": [
                {
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ]
                }
            ]
        }
        result = claude._extract_assistant_text(envelope)
        assert result == "Part 1\nPart 2"

    def test_extract_assistant_text_unknown_shape_raises_error(self):
        """Test that unknown envelope shapes raise clear errors."""
        envelope = {"unknown_key": "value", "another_key": "value2"}
        with pytest.raises(RuntimeError, match="Could not locate assistant text"):
            claude._extract_assistant_text(envelope)

    def test_extract_assistant_text_invalid_type_raises_error(self):
        """Test that non-dict envelopes raise clear errors."""
        with pytest.raises(RuntimeError, match="Unexpected claude envelope type"):
            claude._extract_assistant_text("not a dict")

    def test_run_handles_non_json_stdout(self):
        """Test handling of plain text (non-JSON) stdout."""
        mock_result = Mock()
        mock_result.stdout = """===BUNDLE-BEGIN===
```json
{
  "skills": [],
  "tools": [],
  "permissions": {"allow": [], "deny": []},
  "plan_markdown": "extracted",
  "prompt_recommendations": "test"
}
```
===BUNDLE-END==="""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = claude.run("test", allowed_tools=["Read"])

        assert result["plan_markdown"] == "extracted"

    def test_allowed_tools_formatting(self):
        """Test that allowed_tools are correctly joined with commas."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({
            "result": """===BUNDLE-BEGIN===
```json
{"skills":[],"tools":[],"permissions":{"allow":[],"deny":[]},"plan_markdown":"x","prompt_recommendations":"x"}
```
===BUNDLE-END==="""
        })
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            claude.run("test", allowed_tools=["Tool1", "Tool2", "Tool3"])

        cmd = mock_run.call_args[0][0]
        # Find the allowedTools value
        tools_index = cmd.index("--allowedTools") + 1
        assert cmd[tools_index] == "Tool1,Tool2,Tool3"

    def test_prompt_passed_via_stdin(self):
        """Test that prompt is passed via stdin, not argv."""
        mock_result = Mock()
        mock_result.stdout = """===BUNDLE-BEGIN===
```json
{"skills":[],"tools":[],"permissions":{"allow":[],"deny":[]},"plan_markdown":"x","prompt_recommendations":"x"}
```
===BUNDLE-END==="""
        mock_result.returncode = 0

        test_prompt = "This is my test prompt"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            claude.run(test_prompt, allowed_tools=["Read"])

        # Verify prompt was passed as input, not in command
        assert mock_run.call_args[1]["input"] == test_prompt
        cmd = mock_run.call_args[0][0]
        assert test_prompt not in cmd

    def test_run_called_process_error_403_forbidden(self):
        """Test error handling for 403 Forbidden errors."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = ""
        error.stdout = json.dumps({
            "result": "403 Forbidden - Check your permissions"
        })

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_msg = str(exc_info.value)
        assert "Permission denied" in error_msg
        assert "Check your API key permissions" in error_msg

    def test_run_called_process_error_429_rate_limit(self):
        """Test error handling for rate limit errors."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = ""
        error.stdout = json.dumps({
            "result": "Rate limit exceeded - please try again later"
        })

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_msg = str(exc_info.value)
        assert "Rate limit exceeded" in error_msg
        assert "try again later" in error_msg

    def test_run_called_process_error_with_401_in_stderr(self):
        """Test error handling when 401 appears in stderr."""
        error = subprocess.CalledProcessError(1, ["claude"])
        error.stderr = "Error 401: Unauthorized"
        error.stdout = ""

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                claude.run("test", allowed_tools=["Read"])

        error_msg = str(exc_info.value)
        assert "Invalid API key" in error_msg

    def test_run_empty_allowed_tools(self):
        """Test run with empty allowed_tools list."""
        mock_result = Mock()
        mock_result.stdout = json.dumps({
            "result": """===BUNDLE-BEGIN===
{"skills":[],"tools":[],"permissions":{"allow":[],"deny":[]},"plan_markdown":"test","prompt_recommendations":"test"}
===BUNDLE-END==="""
        })
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            claude.run("test", allowed_tools=[])

        cmd = mock_run.call_args[0][0]
        tools_index = cmd.index("--allowedTools") + 1
        assert cmd[tools_index] == ""
