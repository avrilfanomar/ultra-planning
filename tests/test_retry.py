from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from ultra_plan._retry import retry
from ultra_plan.agents._errors import is_retryable


def _cpe(stderr: str = "", exit_code: int = 1) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        returncode=exit_code, cmd=["x"], output="", stderr=stderr
    )


def test_is_retryable_rate_limit() -> None:
    assert is_retryable(_cpe(stderr="HTTP 429 rate limit exceeded"))


def test_is_retryable_econnreset() -> None:
    assert is_retryable(_cpe(stderr="socket error: ECONNRESET"))


def test_is_retryable_timeout_word() -> None:
    assert is_retryable(_cpe(stderr="upstream timeout"))


def test_is_not_retryable_auth_failure() -> None:
    assert not is_retryable(_cpe(stderr="Invalid API key"))


def test_retry_succeeds_after_transient_failures() -> None:
    sleep_calls: list[float] = []

    def _sleep(secs: float) -> None:
        sleep_calls.append(secs)

    attempts: list[int] = []

    def _fn() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise _cpe(stderr="429 rate limit")
        return "ok"

    result = retry(
        _fn,
        max_attempts=5,
        is_retryable=lambda e: isinstance(e, subprocess.CalledProcessError) and is_retryable(e),
        sleep=_sleep,
        rand=lambda lo, hi: hi,  # deterministic: pick the cap
    )
    assert result == "ok"
    assert len(attempts) == 3
    assert len(sleep_calls) == 2


def test_retry_propagates_non_retryable_immediately() -> None:
    def _fn() -> None:
        raise _cpe(stderr="Invalid API key")

    with pytest.raises(subprocess.CalledProcessError):
        retry(
            _fn,
            max_attempts=5,
            is_retryable=lambda e: isinstance(e, subprocess.CalledProcessError) and is_retryable(e),
            sleep=lambda _s: None,
        )


def test_retry_gives_up_after_max_attempts() -> None:
    attempts: list[int] = []

    def _fn() -> None:
        attempts.append(1)
        raise _cpe(stderr="429 rate limit")

    with pytest.raises(subprocess.CalledProcessError):
        retry(
            _fn,
            max_attempts=3,
            is_retryable=lambda e: isinstance(e, subprocess.CalledProcessError) and is_retryable(e),
            sleep=lambda _s: None,
        )
    assert len(attempts) == 3


def test_retry_logs_warning_for_each_retry(caplog) -> None:
    attempts: list[int] = []

    def _fn() -> str:
        attempts.append(1)
        if len(attempts) < 2:
            raise _cpe(stderr="429 rate limit")
        return "ok"

    caplog.set_level("WARNING", logger="ultra_plan._retry")
    retry(
        _fn,
        max_attempts=3,
        is_retryable=lambda e: isinstance(e, subprocess.CalledProcessError) and is_retryable(e),
        sleep=lambda _s: None,
        rand=lambda lo, hi: 0.0,
    )
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "retry 1/3" in warnings[0].getMessage()


def test_preflight_claude_retries_on_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from ultra_plan import _retry as retry_mod
    from ultra_plan.agents import claude as claude_agent

    calls: list[int] = []

    def _fake_run(*args, **kwargs):
        calls.append(1)
        if len(calls) < 2:
            raise _cpe(stderr="HTTP 429 rate limit")
        return MagicMock(returncode=0, stdout='{"result": "ignored"}', stderr="")

    monkeypatch.setattr(claude_agent.subprocess, "run", _fake_run)
    monkeypatch.setattr(claude_agent, "extract_bundle", lambda _text: {"task": "x"})
    # Neutralize real sleep + jitter so the test runs instantly.
    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(retry_mod.random, "uniform", lambda _lo, _hi: 0.0)

    result = claude_agent.run("prompt", allowed_tools=[])
    assert result == {"task": "x"}
    assert len(calls) == 2
