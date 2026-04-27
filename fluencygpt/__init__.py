"""Repository-local package shim for src-layout imports.

This lets `python -m fluencygpt` work from the project root without requiring
manual PYTHONPATH setup.
"""

from __future__ import annotations

from pathlib import Path

# Include the real package path (src/fluencygpt) in this package search path.
_SRC_PACKAGE_DIR = Path(__file__).resolve().parent.parent / "src" / "fluencygpt"
if _SRC_PACKAGE_DIR.exists():
    __path__.append(str(_SRC_PACKAGE_DIR))
