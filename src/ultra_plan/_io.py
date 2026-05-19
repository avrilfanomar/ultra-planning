from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` atomically.

    Writes to `<path>.tmp` first, then `os.replace`s into place so a crash
    mid-write cannot leave a half-written file at the destination. Also drops
    the `.tmp` artifact if the write itself fails.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content)
        os.replace(tmp, path)
    except BaseException:
        # Best-effort cleanup so failed writes don't leave .tmp turds behind.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
