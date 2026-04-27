"""Repository-local module entrypoint for src-layout package.

Delegates execution to src/fluencygpt/__main__.py so local runs are simple:
    python -m fluencygpt
"""

from __future__ import annotations

from pathlib import Path
import runpy


def main() -> None:
    src_main = Path(__file__).resolve().parent.parent / "src" / "fluencygpt" / "__main__.py"
    if not src_main.exists():
        raise RuntimeError(f"Missing entrypoint: {src_main}")

    runpy.run_path(str(src_main), run_name="__main__")


if __name__ == "__main__":
    main()
