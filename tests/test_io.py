from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ultra_plan._io import atomic_write_text


def test_atomic_write_text_writes_content(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    atomic_write_text(dest, "hello")
    assert dest.read_text() == "hello"
    assert not (tmp_path / "out.txt.tmp").exists()


def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    dest.write_text("old")
    atomic_write_text(dest, "new")
    assert dest.read_text() == "new"


def test_atomic_write_text_cleans_up_tmp_on_replace_failure(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    with patch("ultra_plan._io.os.replace", side_effect=OSError("boom")):
        with pytest.raises(OSError, match="boom"):
            atomic_write_text(dest, "payload")
    assert not (tmp_path / "out.txt.tmp").exists()
    assert not dest.exists()
