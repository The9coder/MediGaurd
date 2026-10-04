"""Regression tests for app-level security controls."""

import pytest


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "dob": "1980-01-02", "gender": "F", "diagnosis": "ok"},
        {"name": "Jane", "dob": "not-a-date", "gender": "F", "diagnosis": "ok"},
        {"name": "Jane", "dob": "1980-01-02", "gender": "X", "diagnosis": "ok"},
        {"name": "Jane", "dob": "1980-01-02", "gender": "F", "diagnosis": "x" * 256},
        ["not", "an", "object"],
    ],
)
def test_patient_creation_rejects_invalid_payload(client, auth_headers, payload):
    response = client.post("/patients", headers=auth_headers, json=payload)
    assert response.status_code == 400


def test_mutating_authenticated_request_requires_csrf(client, auth_headers):
    response = client.post(
        "/patients",
        json={"name": "Jane", "dob": "1980-01-02", "gender": "F"},
    )
    assert response.status_code == 403


def test_not_found_and_method_not_allowed(client):
    assert client.get("/definitely-missing").status_code == 404
    assert client.post("/health").status_code == 405


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


def test_security_headers_and_no_store_are_set(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
