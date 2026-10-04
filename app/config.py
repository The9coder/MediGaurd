"""
app/config.py – MediGuard Application Configuration
=====================================================
All secrets must come from environment variables in production.
The defaults here are for local development only.
"""

from __future__ import annotations

import os
import secrets


class Config:
    """Base configuration. Override with environment variables."""

    # Flask
    SECRET_KEY: str = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
    TESTING: bool = False

    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/mediguard"
    )
    DB_SSLMODE: str = os.environ.get("DB_SSLMODE", "prefer")

    # OIDC identity provider
    OIDC_ISSUER: str = os.environ.get("OIDC_ISSUER", "").rstrip("/")
    OIDC_CLIENT_ID: str = os.environ.get("OIDC_CLIENT_ID", "")
    OIDC_CLIENT_SECRET: str = os.environ.get("OIDC_CLIENT_SECRET", "")
    OIDC_ADMIN_ROLE: str = os.environ.get("OIDC_ADMIN_ROLE", "admin")
    OIDC_ROLE_CLAIM: str = os.environ.get("OIDC_ROLE_CLAIM", "roles")
    TRUSTED_PROXY_HOPS: int = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))
    TRUSTED_HOSTS: list[str] | None = [
        host.strip()
        for host in os.environ.get("TRUSTED_HOSTS", "").split(",")
        if host.strip()
    ] or None

    # Security / hardening defaults
    SESSION_COOKIE_SECURE: bool = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    MAX_CONTENT_LENGTH: int = int(os.environ.get("MAX_CONTENT_LENGTH", str(64 * 1024)))
    REDIS_URL: str = os.environ.get("REDIS_URL", "memory://")
    ENABLE_PATIENT_RECORDS: bool = os.environ.get(
        "ENABLE_PATIENT_RECORDS", "false"
    ).lower() == "true"
    PATIENT_DATA_GOVERNANCE_REFERENCE: str = os.environ.get(
        "PATIENT_DATA_GOVERNANCE_REFERENCE", ""
    )
    ENABLE_PREDICTIONS: bool = os.environ.get("ENABLE_PREDICTIONS", "false").lower() == "true"
    MODEL_SHA256: str = os.environ.get("MODEL_SHA256", "")
    MODEL_VALIDATION_REFERENCE: str = os.environ.get("MODEL_VALIDATION_REFERENCE", "")

    # Logging
    LOG_FILE: str = os.environ.get("LOG_FILE", "logs/access.log")
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # Model – points to the real trained pipeline
    MODEL_PATH: str = os.environ.get("MODEL_PATH", "ml/model/heart_model.joblib")


class DevelopmentConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    # Tests use the real model unless overridden in conftest
    MODEL_PATH = os.environ.get("MODEL_PATH", "ml/model/heart_model.joblib")


class ProductionConfig(Config):
    DEBUG = False


config: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing":     TestingConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}


def environment_overrides() -> dict[str, object]:
    """Read environment-backed settings at app creation time, not import time."""
    boolean_keys = {
        "DEBUG",
        "SESSION_COOKIE_SECURE",
        "ENABLE_PREDICTIONS",
    }
    integer_keys = {"MAX_CONTENT_LENGTH"}
    keys = (
        "SECRET_KEY", "DEBUG", "DATABASE_URL", "DB_SSLMODE", "OIDC_ISSUER",
        "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_ADMIN_ROLE",
        "OIDC_ROLE_CLAIM", "SESSION_COOKIE_SECURE", "MAX_CONTENT_LENGTH",
        "REDIS_URL", "ENABLE_PATIENT_RECORDS", "PATIENT_DATA_GOVERNANCE_REFERENCE",
        "ENABLE_PREDICTIONS", "MODEL_SHA256",
        "MODEL_VALIDATION_REFERENCE", "LOG_FILE", "LOG_LEVEL", "MODEL_PATH",
        "TRUSTED_PROXY_HOPS", "TRUSTED_HOSTS",
    )
    overrides: dict[str, object] = {}
    for key in keys:
        if key not in os.environ:
            continue
        value: object = os.environ[key]
        if key in boolean_keys:
            value = os.environ[key].lower() == "true"
        elif key in integer_keys or key == "TRUSTED_PROXY_HOPS":
            value = int(os.environ[key])
        elif key == "TRUSTED_HOSTS":
            value = [host.strip() for host in os.environ[key].split(",") if host.strip()]
        elif key == "OIDC_ISSUER":
            value = os.environ[key].rstrip("/")
        overrides[key] = value
    return overrides
