from __future__ import annotations

import json
import subprocess

from ultra_plan.agents._errors import classify_cli_error


def _err(stdout: str = "", stderr: str = "", code: int = 1) -> subprocess.CalledProcessError:
    e = subprocess.CalledProcessError(code, ["x"])
    e.stdout = stdout
    e.stderr = stderr
    return e


def test_classify_401_invalid_api_key_for_opencode():
    err = _err(stdout=json.dumps({"result": "Invalid API key"}))
    out = classify_cli_error(err, cli_name="opencode")
    assert "Invalid API key" in str(out)
    assert "opencode CLI failed" in str(out)


def test_classify_403_forbidden_for_opencode():
    err = _err(stderr="HTTP 403 Forbidden")
    out = classify_cli_error(err, cli_name="opencode")
    assert "Permission denied" in str(out)


def test_classify_429_rate_limit_for_opencode():
    err = _err(stderr="429 rate limit exceeded")
    out = classify_cli_error(err, cli_name="opencode")
    assert "Rate limit exceeded" in str(out)


def test_classify_generic_for_opencode():
    err = _err(stderr="boom", code=42)
    out = classify_cli_error(err, cli_name="opencode")
    assert "opencode CLI failed with exit code 42" in str(out)
    assert "boom" in str(out)


def test_classify_truncates_long_stderr():
    err = _err(stderr="x" * 1000)
    out = classify_cli_error(err, cli_name="claude")
    msg = str(out)
    assert len(msg) < 700
