"""
Tests for GET /health
"""

from unittest.mock import MagicMock, patch

from psycopg import OperationalError


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_response_body(client):
    data = client.get("/health").get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "mediguard-api"
    assert "version" in data


@patch("app.routes.health.get_db")
def test_readiness_checks_database(mock_get_db, client):
    mock_get_db.return_value.cursor.return_value = MagicMock()
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ready"}


@patch("app.routes.health.get_db", side_effect=OperationalError("db unavailable"))
def test_readiness_fails_without_database(mock_get_db, client):
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.get_json() == {"status": "unavailable"}
