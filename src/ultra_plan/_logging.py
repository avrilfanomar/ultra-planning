from __future__ import annotations

import logging
import sys

_INFO_FORMAT = "[ultra-plan] %(message)s"
_DEBUG_FORMAT = "[ultra-plan] %(levelname)s %(name)s: %(message)s"

_configured = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def configure_logging(*, quiet: bool = False, verbose: bool = False, debug: bool = False) -> None:
    """Configure the root and `ultra_plan` loggers to write to stderr.

    Precedence (highest to lowest): debug > verbose > quiet > default(INFO).
    `--debug` enables DEBUG everywhere; `--verbose` only for `ultra_plan.*`.
    Re-entrant: safe to call multiple times; replaces existing ultra-plan handlers.
    """
    global _configured

    if debug:
        root_level = logging.DEBUG
        pkg_level = logging.DEBUG
        fmt = _DEBUG_FORMAT
    elif verbose:
        root_level = logging.WARNING
        pkg_level = logging.DEBUG
        fmt = _DEBUG_FORMAT
    elif quiet:
        root_level = logging.WARNING
        pkg_level = logging.WARNING
        fmt = _INFO_FORMAT
    else:
        root_level = logging.WARNING
        pkg_level = logging.INFO
        fmt = _INFO_FORMAT

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt))
    handler.set_name("ultra_plan_stderr")

    root = logging.getLogger()
    root.setLevel(root_level)
    for h in list(root.handlers):
        if h.get_name() == "ultra_plan_stderr":
            root.removeHandler(h)
    root.addHandler(handler)

    pkg = logging.getLogger("ultra_plan")
    pkg.setLevel(pkg_level)
    pkg.propagate = True

    _configured = True
