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

    # JWT
    JWT_SECRET: str = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
    JWT_EXPIRY_HOURS: int = int(os.environ.get("JWT_EXPIRY_HOURS", "1"))

    # Database
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int = int(os.environ.get("DB_PORT", "3306"))
    DB_USER: str = os.environ.get("DB_USER", "mediguard")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "mediguard_pass")
    DB_NAME: str = os.environ.get("DB_NAME", "mediguard_db")

    INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "")

    # Logging
    LOG_FILE: str = os.environ.get("LOG_FILE", "logs/access.log")
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # Model – points to the real trained pipeline
    MODEL_PATH: str = os.environ.get("MODEL_PATH", "ml/model/heart_model.joblib")


class DevelopmentConfig(Config):
    DEBUG = True


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
