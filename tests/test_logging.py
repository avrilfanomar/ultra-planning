from __future__ import annotations

import logging

from ultra_plan._logging import configure_logging, get_logger


def _reset_root() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        if h.get_name() == "ultra_plan_stderr":
            root.removeHandler(h)


def test_default_level_is_info_for_package() -> None:
    _reset_root()
    configure_logging(quiet=False, verbose=False, debug=False)
    assert logging.getLogger("ultra_plan").getEffectiveLevel() == logging.INFO


def test_quiet_raises_package_level_to_warning() -> None:
    _reset_root()
    configure_logging(quiet=True, verbose=False, debug=False)
    assert logging.getLogger("ultra_plan").getEffectiveLevel() == logging.WARNING


def test_verbose_enables_debug_for_package_only() -> None:
    _reset_root()
    configure_logging(quiet=False, verbose=True, debug=False)
    assert logging.getLogger("ultra_plan").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger().getEffectiveLevel() == logging.WARNING


def test_debug_enables_debug_globally() -> None:
    _reset_root()
    configure_logging(quiet=False, verbose=False, debug=True)
    assert logging.getLogger("ultra_plan").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG


def test_log_messages_emitted_to_stderr(capsys) -> None:
    _reset_root()
    configure_logging(quiet=False, verbose=False, debug=False)
    get_logger("ultra_plan.test").info("hello world")
    captured = capsys.readouterr()
    assert "hello world" in captured.err
    assert "[ultra-plan]" in captured.err
    assert captured.out == ""


def test_quiet_suppresses_info(capsys) -> None:
    _reset_root()
    configure_logging(quiet=True, verbose=False, debug=False)
    get_logger("ultra_plan.test").info("muted")
    captured = capsys.readouterr()
    assert "muted" not in captured.err


def test_reconfigure_does_not_duplicate_handlers() -> None:
    _reset_root()
    configure_logging(quiet=False, verbose=False, debug=False)
    configure_logging(quiet=False, verbose=False, debug=False)
    root = logging.getLogger()
    matching = [h for h in root.handlers if h.get_name() == "ultra_plan_stderr"]
    assert len(matching) == 1
