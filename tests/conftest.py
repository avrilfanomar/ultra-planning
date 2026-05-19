from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize backoff sleep in `ultra_plan._retry` for every test.

    Without this, tests that inject a retryable CalledProcessError pay 2-30s
    of real wall-clock sleep per case. The fixture is autouse so the suite
    stays fast by default.

    If a future test needs to assert on real sleep behaviour, re-patch inside
    the test body — pytest applies the last `monkeypatch.setattr` on the same
    target, so the override is local to that test. Or pass `sleep=` explicitly
    to `retry()` to bypass the global default entirely.
    """
    from ultra_plan import _retry as _retry_mod

    monkeypatch.setattr(_retry_mod.time, "sleep", lambda _s: None)
