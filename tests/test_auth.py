"""
Tests for POST /login
"""
from unittest.mock import MagicMock, patch

from werkzeug.security import check_password_hash


def test_login_success(client):
    resp = client.post(
        "/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "token" in data
    assert data["role"] == "admin"


def test_login_wrong_password(client):
    resp = client.post(
        "/login",
        json={"username": "admin", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_login_unknown_user(client):
    with patch("app.routes.auth.get_db") as mock_get_db:
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        mock_get_db.return_value.cursor.return_value = cursor
        resp = client.post("/login", json={"username": "hacker", "password": "anything"})
    assert resp.status_code == 401


def test_login_missing_body(client):
    resp = client.post("/login", data="", content_type="application/json")
    assert resp.status_code == 401


def test_login_clinician(client):
    resp = client.post(
        "/login",
        json={"username": "clinician", "password": "test-clinician-password"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "clinician"


@patch("app.routes.auth.get_db")
def test_register_creates_hashed_clinician_account(mock_get_db, client):
    cursor = MagicMock()
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post(
        "/register",
        json={"username": "new_clinician", "password": "safe-password"},
    )

    assert response.status_code == 201
    assert response.get_json()["role"] == "clinician"
    insert_args = cursor.execute.call_args_list[-1].args
    assert "INSERT INTO app_users" in insert_args[0]
    saved_hash = insert_args[1][1]
    assert saved_hash != "safe-password"
    assert check_password_hash(saved_hash, "safe-password")


def test_register_rejects_short_password(client):
    response = client.post(
        "/register",
        json={"username": "new_clinician", "password": "short"},
    )
    assert response.status_code == 400
