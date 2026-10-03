import pytest


def test_production_requires_explicit_secrets(monkeypatch):
    from app.factory import create_app

    for name in ("SECRET_KEY", "JWT_SECRET", "DB_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="Production configuration requires"):
        create_app("production")


def test_production_rejects_short_signing_secrets(monkeypatch):
    from app.factory import create_app

    monkeypatch.setenv("SECRET_KEY", "short")
    monkeypatch.setenv("JWT_SECRET", "also-short")
    monkeypatch.setenv("DB_PASSWORD", "strong-db-password")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        create_app("production")


def test_production_uses_environment_secrets(monkeypatch):
    from app.factory import create_app

    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv("JWT_SECRET", "j" * 32)
    monkeypatch.setenv("DB_PASSWORD", "db-password-from-secret-store")

    app = create_app("production")

    assert app.config["SECRET_KEY"] == "s" * 32
    assert app.config["JWT_SECRET"] == "j" * 32
    assert app.config["DB_PASSWORD"] == "db-password-from-secret-store"
    assert app.config["DEBUG"] is False


def test_production_rejects_demo_accounts(monkeypatch):
    from app.factory import create_app

    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv("JWT_SECRET", "j" * 32)
    monkeypatch.setenv("DB_PASSWORD", "db-password-from-secret-store")
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "local-only-demo-password")

    with pytest.raises(RuntimeError, match="Demo accounts must be disabled"):
        create_app("production")


def test_internal_error_response_does_not_expose_exception(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def fail():
        raise RuntimeError("private internal detail")

    app.add_url_rule("/_test/error", view_func=fail)
    response = app.test_client().get("/_test/error")

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}
    assert b"private internal detail" not in response.data
    assert b"traceback" not in response.data.lower()


def test_demo_account_is_disabled_without_configured_password(client, app):
    app.config["DEMO_ADMIN_PASSWORD"] = ""

    response = client.post(
        "/login",
        json={"username": "admin", "password": "anything"},
    )

    assert response.status_code == 401
