"""Tests for the OIDC-backed browser session."""


def test_oidc_login_is_unavailable_without_provider_config(client):
    response = client.get("/auth/login")
    assert response.status_code == 503
    assert "identity provider" in response.get_json()["error"].lower()


def test_session_endpoint_does_not_authenticate_anonymous_user(client):
    response = client.get("/auth/session")
    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}


def test_session_endpoint_returns_csrf_token_for_authenticated_user(client, auth_headers):
    response = client.get("/auth/session")
    result = response.get_json()
    assert response.status_code == 200
    assert result["authenticated"] is True
    assert result["role"] == "admin"
    assert result["csrf_token"] == auth_headers["X-CSRF-Token"]


def test_logout_requires_csrf_token(client, auth_headers):
    response = client.post("/auth/logout")
    assert response.status_code == 403


def test_logout_clears_authenticated_session(client, auth_headers):
    response = client.post("/auth/logout", headers=auth_headers)
    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}
    assert client.get("/auth/session").get_json() == {"authenticated": False}


def test_local_password_routes_are_removed(client):
    login = client.post("/login", json={"username": "admin", "password": "admin"})
    register = client.post("/register", json={"username": "new", "password": "password"})
    assert login.status_code == 404
    assert register.status_code == 404
