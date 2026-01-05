from __future__ import annotations

import argparse

from dotenv import load_dotenv

from fluencygpt.app import create_app
from fluencygpt.config import get_settings


def main() -> None:
    """Entrypoint: `python -m fluencygpt`.

    Supports running with Flask dev server or Waitress.
    """

    load_dotenv(override=False)
    settings = get_settings()

    parser = argparse.ArgumentParser(description="FluencyGPT Flask backend")
    parser.add_argument(
        "--serve",
        choices=["flask", "waitress"],
        default="flask",
        help="Server backend (default: flask dev server)",
    )
    args = parser.parse_args()

    app = create_app()

    if args.serve == "waitress":
        from waitress import serve

        serve(app, host=settings.host, port=settings.port)
    else:
        app.run(host=settings.host, port=settings.port, debug=True)


if __name__ == "__main__":
    main()
