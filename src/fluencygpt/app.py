from __future__ import annotations

import logging
import pathlib

from flask import Flask, send_from_directory

from fluencygpt.config import get_settings
from fluencygpt.routes.api import api_bp
from fluencygpt.routes.voice import voice_bp

# Project root (where FrontendUI.html lives).
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        # Respect existing handlers but make sure our INFO logs aren't dropped.
        root.setLevel(logging.INFO)
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app() -> Flask:
    """Application factory.

    This pattern keeps configuration/testability clean for a final-year project.
    """

    settings = get_settings()

    _configure_logging()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes

    app.register_blueprint(api_bp)
    app.register_blueprint(voice_bp)

    # ── CORS (allow any origin for local dev / demo) ──────────────────────
    @app.after_request
    def _add_cors_headers(response):  # noqa: ANN001, ANN202
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    # ── Serve FrontendUI.html at root ─────────────────────────────────────
    @app.route("/")
    def index():  # noqa: ANN202
        return send_from_directory(str(_PROJECT_ROOT), "FrontendUI.html")

    return app

