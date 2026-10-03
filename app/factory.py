"""
app/factory.py – Flask Application Factory
============================================
Creates the Flask app, wires up blueprints, configures structured
access logging (JSON lines) and global error handlers.
"""

from __future__ import annotations

import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request

from app.config import config


def create_app(config_name: str = "default") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    if config_name == "production":
        required_secrets = ("SECRET_KEY", "JWT_SECRET", "DB_PASSWORD")
        missing = [name for name in required_secrets if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "Production configuration requires: " + ", ".join(missing)
            )
        weak_keys = [
            name
            for name in ("SECRET_KEY", "JWT_SECRET")
            if len(os.environ[name]) < 32
        ]
        if weak_keys:
            raise RuntimeError(
                "Production secrets must be at least 32 characters: "
                + ", ".join(weak_keys)
            )
        configured_demo_accounts = [
            name
            for name in ("DEMO_ADMIN_PASSWORD", "DEMO_CLINICIAN_PASSWORD")
            if os.environ.get(name)
        ]
        if configured_demo_accounts:
            raise RuntimeError(
                "Demo accounts must be disabled in production: "
                + ", ".join(configured_demo_accounts)
            )
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
        app.config["JWT_SECRET"] = os.environ["JWT_SECRET"]
        app.config["DB_PASSWORD"] = os.environ["DB_PASSWORD"]
        app.config["DEMO_ADMIN_PASSWORD"] = ""
        app.config["DEMO_CLINICIAN_PASSWORD"] = ""

    # ── Log directory ─────────────────────────────────────────────────────────
    os.makedirs("logs", exist_ok=True)

    # ── Structured access logger (JSON lines) ─────────────────────────────────
    access_logger = logging.getLogger("mediguard.access")
    access_logger.setLevel(logging.INFO)
    if not access_logger.handlers:
        handler = RotatingFileHandler(
            app.config["LOG_FILE"],
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        access_logger.addHandler(handler)
    app.access_logger = access_logger  # type: ignore[attr-defined]

    # ── Request hooks for access logging ─────────────────────────────────────
    @app.before_request
    def _start_timer() -> None:
        request._start_time = time.time()  # type: ignore[attr-defined]

    @app.after_request
    def _log_access(response):
        duration_ms = round((time.time() - getattr(request, "_start_time", time.time())) * 1000, 2)
        jwt_payload = getattr(request, "jwt_payload", {})
        user = jwt_payload.get("sub", "anonymous") if jwt_payload else "anonymous"

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ip": request.remote_addr,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "user": user,
            "duration_ms": duration_ms,
        }
        app.access_logger.info(json.dumps(record))
        return response

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.predict import predict_bp
    from app.routes.patients import patients_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(predict_bp)
    app.register_blueprint(patients_bp)

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "Internal server error"}), 500

    return app
