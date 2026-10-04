"""
app/factory.py – Flask Application Factory
============================================
Creates the Flask app, wires up blueprints, configures structured
access logging (JSON lines) and global error handlers.
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from tempfile import gettempdir
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from cachelib import FileSystemCache
from flask import Flask, jsonify, request
from flask_limiter.errors import RateLimitExceeded
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix
from psycopg import Error as DatabaseError
from psycopg_pool import PoolTimeout
from redis import Redis

from app.config import config, environment_overrides
from app.extensions import limiter
from app.database import close_db, init_database


def create_app(config_name: str = "default") -> Flask:
    """Create and configure the Flask application."""
    if config_name not in config:
        raise ValueError(f"Unknown configuration: {config_name}")
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    app.config.from_mapping(environment_overrides())
    app.config["DEPLOYMENT_ENV"] = config_name
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600
    app.config["SESSION_PERMANENT"] = True
    app.config["RATELIMIT_STORAGE_URI"] = app.config["REDIS_URL"]
    if app.config["REDIS_URL"] != "memory://":
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = Redis.from_url(app.config["REDIS_URL"])
    else:
        app.config["SESSION_TYPE"] = "cachelib"
        app.config["SESSION_CACHELIB"] = FileSystemCache(
            str(Path(gettempdir()) / "mediguard-test-sessions"),
            threshold=1000,
        )
    Session(app)
    if config_name == "production":
        app.config["DEBUG"] = False
        app.config["TESTING"] = False
        required_secrets = (
            "SECRET_KEY",
            "OIDC_ISSUER",
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "DATABASE_URL",
            "REDIS_URL",
            "TRUSTED_PROXY_HOPS",
            "TRUSTED_HOSTS",
        )
        missing = [name for name in required_secrets if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "Production configuration requires: " + ", ".join(missing)
            )
        if len(os.environ["SECRET_KEY"]) < 32:
            raise RuntimeError(
                "Production SECRET_KEY must be at least 32 characters"
            )
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
        if not app.config["OIDC_ISSUER"].startswith("https://"):
            raise RuntimeError("Production OIDC issuer must use HTTPS")
        if not app.config["REDIS_URL"].startswith("rediss://"):
            raise RuntimeError("Production Redis connections must use TLS")
        if app.config["DB_SSLMODE"] not in {"require", "verify-ca", "verify-full"}:
            raise RuntimeError("Production database connections must use TLS")
        if app.config["TRUSTED_PROXY_HOPS"] < 1 or not app.config["TRUSTED_HOSTS"]:
            raise RuntimeError(
                "Production requires trusted proxy hops and an explicit trusted-host list"
            )
        if (
            app.config["ENABLE_PATIENT_RECORDS"]
            and not app.config["PATIENT_DATA_GOVERNANCE_REFERENCE"]
        ):
            raise RuntimeError(
                "Patient records require an approved data-governance and retention reference"
            )
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config["TRUSTED_PROXY_HOPS"],
            x_proto=app.config["TRUSTED_PROXY_HOPS"],
            x_host=app.config["TRUSTED_PROXY_HOPS"],
            x_port=app.config["TRUSTED_PROXY_HOPS"],
        )
        if app.config["ENABLE_PREDICTIONS"] and not app.config["MODEL_SHA256"]:
            raise RuntimeError(
                "Production predictions require a SHA-256-pinned validated model"
            )
        if app.config["ENABLE_PREDICTIONS"]:
            model_path = app.config["MODEL_PATH"]
            if not app.config["MODEL_VALIDATION_REFERENCE"] or not os.path.isfile(model_path):
                raise RuntimeError(
                    "Production predictions require an installed model and validation reference"
                )
            with open(model_path, "rb") as model_file:
                model_hash = hashlib.file_digest(model_file, "sha256").hexdigest()
            if model_hash.lower() != app.config["MODEL_SHA256"].lower():
                raise RuntimeError("Production model SHA-256 does not match configuration")

    # ── Structured access logger (JSON lines; endpoint-only to avoid PHI) ─────
    access_logger = logging.getLogger("mediguard.access")
    access_logger.setLevel(logging.INFO)
    if not access_logger.handlers:
        if app.config["LOG_FILE"] == "-":
            handler = logging.StreamHandler()
        else:
            log_path = app.config["LOG_FILE"]
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
            handler = RotatingFileHandler(
                log_path,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        handler.setFormatter(logging.Formatter("%(message)s"))
        access_logger.addHandler(handler)
    app.access_logger = access_logger  # type: ignore[attr-defined]
    limiter.init_app(app)
    init_database(app)
    app.teardown_appcontext(close_db)

    if app.config["OIDC_ISSUER"] and app.config["OIDC_CLIENT_ID"]:
        oauth = OAuth(app)
        oauth.register(
            name="oidc",
            client_id=app.config["OIDC_CLIENT_ID"],
            client_secret=app.config["OIDC_CLIENT_SECRET"],
            server_metadata_url=(
                app.config["OIDC_ISSUER"] + "/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid profile email"},
        )
        app.extensions["oidc_client"] = oauth.create_client("oidc")

    # ── Request hooks for access logging ─────────────────────────────────────
    @app.before_request
    def _start_timer() -> None:
        request._start_time = time.time()  # type: ignore[attr-defined]

    @app.after_request
    def _log_access(response):
        duration_ms = round((time.time() - getattr(request, "_start_time", time.time())) * 1000, 2)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "endpoint": request.endpoint,
            "status": response.status_code,
            "role": session_role(),
            "duration_ms": duration_ms,
        }
        app.access_logger.info(json.dumps(record))
        return response

    @app.before_request
    def _require_csrf_token():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            from flask import session

            if session.get("principal"):
                import hmac

                expected = session.get("csrf_token", "")
                supplied = request.headers.get("X-CSRF-Token", "")
                if not expected or not hmac.compare_digest(expected, supplied):
                    return jsonify({"error": "CSRF token missing or invalid"}), 403

    @app.after_request
    def _add_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if config_name == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
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
    app.register_error_handler(RateLimitExceeded, lambda _error: (
        jsonify({"error": "Rate limit exceeded; try again later"}), 429
    ))

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(DatabaseError)
    @app.errorhandler(PoolTimeout)
    def database_unavailable(error):
        app.logger.error("Database operation failed (%s)", type(error).__name__)
        return jsonify({"error": "Data service is temporarily unavailable"}), 503

    @app.errorhandler(500)
    def internal_error(e):
        original = getattr(e, "original_exception", None)
        app.logger.error(
            "Unhandled server error (%s)",
            type(original).__name__ if original else "InternalServerError",
        )
        return jsonify({"error": "Internal server error"}), 500

    return app


def session_role() -> str:
    from flask import session

    principal = session.get("principal", {})
    return principal.get("role", "anonymous") if isinstance(principal, dict) else "anonymous"
