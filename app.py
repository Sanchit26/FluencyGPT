from __future__ import annotations

import pathlib
import sys

from dotenv import load_dotenv


def _ensure_src_on_path() -> None:
    root = pathlib.Path(__file__).resolve().parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> None:
    """Run the FluencyGPT Flask app.

    This entrypoint exists so the project can be started with:
      python app.py

    The package code lives under src/, so we add it to sys.path for local runs.
    """

    _ensure_src_on_path()
    load_dotenv(override=False)

    from fluencygpt.app import create_app
    from fluencygpt.config import get_settings

    settings = get_settings()
    app = create_app()
    app.run(host=settings.host, port=settings.port, debug=True)


if __name__ == "__main__":
    main()
