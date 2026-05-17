"""Test version consistency across the project."""

from __future__ import annotations

import re
import tomli
from pathlib import Path


def test_version_consistency():
    """Ensure __version__ in __init__.py matches pyproject.toml."""
    # Read version from pyproject.toml
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"

    with open(pyproject_path, "rb") as f:
        pyproject_data = tomli.load(f)

    pyproject_version = pyproject_data["project"]["version"]

    # Read version from __init__.py
    init_path = project_root / "src" / "ultra_plan" / "__init__.py"
    init_content = init_path.read_text()

    # Extract __version__ from __init__.py
    version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_content)
    assert version_match, "Could not find __version__ in __init__.py"

    init_version = version_match.group(1)

    # Verify they match
    assert init_version == pyproject_version, (
        f"Version mismatch: __init__.py has {init_version!r}, "
        f"but pyproject.toml has {pyproject_version!r}"
    )
