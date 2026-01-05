from __future__ import annotations

from flask import Flask

from fluencygpt.config import get_settings
from fluencygpt.routes.api import api_bp


def create_app() -> Flask:
    """Application factory.

    This pattern keeps configuration/testability clean for a final-year project.
    """

    settings = get_settings()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes

    app.register_blueprint(api_bp)

    return app
