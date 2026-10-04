"""Tests for production configuration and OIDC role handling."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


PRODUCTION_ENV = (
    "SECRET_KEY",
    "OIDC_ISSUER",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
    "DB_SSLMODE",
    "TRUSTED_PROXY_HOPS",
    "TRUSTED_HOSTS",
)


def set_production_environment(monkeypatch):
    values = {
        "SECRET_KEY": "s" * 40,
        "OIDC_ISSUER": "https://idp.example.test",
        "OIDC_CLIENT_ID": "mediguard",
        "OIDC_CLIENT_SECRET": "provider-client-secret",
        "DATABASE_URL": "postgresql://app:secret@db/mediguard",
        "REDIS_URL": "rediss://:secret@redis:6379/0",
        "DB_SSLMODE": "verify-full",
        "TRUSTED_PROXY_HOPS": "1",
        "TRUSTED_HOSTS": "mediguard.example.org",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_production_requires_explicit_secrets(monkeypatch):
    from app.factory import create_app

    for name in PRODUCTION_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="Production configuration requires"):
        create_app("production")


def test_production_rejects_short_session_secret(monkeypatch):
    from app.factory import create_app

    set_production_environment(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        create_app("production")


def test_production_requires_tls_for_database(monkeypatch):
    from app.factory import create_app

    set_production_environment(monkeypatch)
    monkeypatch.setenv("DB_SSLMODE", "disable")
    with pytest.raises(RuntimeError, match="must use TLS"):
        create_app("production")


def test_production_uses_explicit_oidc_and_secrets(monkeypatch):
    from app.factory import create_app

    values = set_production_environment(monkeypatch)
    app = create_app("production")
    assert app.config["SECRET_KEY"] == values["SECRET_KEY"]
    assert app.config["OIDC_ISSUER"] == values["OIDC_ISSUER"]
    assert app.config["DATABASE_URL"] == values["DATABASE_URL"]
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_production_prediction_is_disabled_by_default(monkeypatch):
    from app.factory import create_app

    set_production_environment(monkeypatch)
    app = create_app("production")
    assert app.config["ENABLE_PREDICTIONS"] is False


def test_production_prediction_requires_model_reference(monkeypatch):
    from app.factory import create_app

    set_production_environment(monkeypatch)
    monkeypatch.setenv("ENABLE_PREDICTIONS", "true")
    monkeypatch.setenv("MODEL_SHA256", "a" * 64)
    with pytest.raises(RuntimeError, match="validation reference"):
        create_app("production")


@patch("app.routes.auth.get_db")
def test_oidc_callback_maps_only_configured_admin_role(mock_get_db, client, app):
    mock_get_db.return_value.cursor.return_value = MagicMock()
    oidc = MagicMock()
    oidc.authorize_access_token.return_value = {
        "userinfo": {"sub": "clinician-123", "roles": ["admin"]},
    }
    app.config["OIDC_ADMIN_ROLE"] = "admin"
    app.extensions["oidc_client"] = oidc
    response = client.get("/auth/callback")
    assert response.status_code == 302
    session = client.get("/auth/session").get_json()
    assert session["authenticated"] is True
    assert session["role"] == "admin"
    assert session["csrf_token"]


@patch("app.routes.auth.get_db")
def test_oidc_callback_defaults_unrecognized_role_to_clinician(mock_get_db, client, app):
    mock_get_db.return_value.cursor.return_value = MagicMock()
    oidc = MagicMock()
    oidc.authorize_access_token.return_value = {
        "userinfo": {"sub": "clinician-123", "roles": ["billing"]},
    }
    app.extensions["oidc_client"] = oidc
    response = client.get("/auth/callback")
    assert response.status_code == 302
    assert client.get("/auth/session").get_json()["role"] == "clinician"
