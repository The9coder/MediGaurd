"""
Tests for GET /health
"""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_response_body(client):
    data = client.get("/health").get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "mediguard-api"
    assert "version" in data
