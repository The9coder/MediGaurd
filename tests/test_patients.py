"""Tests for scoped patient-record access."""

from unittest.mock import MagicMock, patch

import pytest


FAKE_PATIENT = {
    "id": 1,
    "name": "Jane Doe",
    "dob": "1975-03-12",
    "gender": "F",
    "mrn": "MRN-000001",
    "diagnosis": "Hypertension, Stage 1",
    "assigned_to": "clinician-sub",
}


@patch("app.routes.patients.get_db")
def test_get_patient_success(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = FAKE_PATIENT
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients/1", headers=auth_headers)
    assert response.status_code == 200
    assert response.get_json()["mrn"] == "MRN-000001"


@patch("app.routes.patients.get_db")
def test_get_patient_not_found(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients/9999", headers=auth_headers)
    assert response.status_code == 404


def test_get_patient_requires_auth(client):
    assert client.get("/patients/1").status_code == 401


@patch("app.routes.patients.get_db")
def test_patient_list_is_scoped_to_oidc_subject(mock_get_db, client, clinician_headers):
    cursor = MagicMock()
    cursor.fetchall.return_value = [FAKE_PATIENT]
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients", headers=clinician_headers)

    assert response.status_code == 200
    assert response.get_json()["patients"] == [FAKE_PATIENT]
    assert response.get_json()["next_after_id"] is None
    query, params = cursor.execute.call_args_list[0].args
    assert "WHERE assigned_to = %s" in query
    assert "ORDER BY id ASC LIMIT %s" in query
    assert params == ("clinician-sub", 0, 100)


def test_patient_list_rejects_invalid_pagination(client, clinician_headers):
    response = client.get(
        "/patients?limit=101",
        headers=clinician_headers,
    )
    assert response.status_code == 400


def test_patient_list_rejects_non_integer_pagination(client, clinician_headers):
    response = client.get("/patients?after_id=first", headers=clinician_headers)
    assert response.status_code == 400


@patch("app.routes.patients.get_db")
def test_patient_list_returns_cursor_for_next_page(
    mock_get_db, client, clinician_headers
):
    cursor = MagicMock()
    cursor.fetchall.return_value = [FAKE_PATIENT]
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients?limit=1", headers=clinician_headers)

    assert response.status_code == 200
    assert response.get_json()["next_after_id"] == FAKE_PATIENT["id"]


@patch("app.routes.patients.get_db")
def test_admin_patient_list_is_paginated(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients?after_id=20&limit=10", headers=auth_headers)

    assert response.status_code == 200
    query, params = cursor.execute.call_args_list[0].args
    assert "WHERE id > %s ORDER BY id ASC LIMIT %s" in query
    assert params == (20, 10)


@patch("app.routes.patients.get_db")
def test_create_patient_assigns_record_to_oidc_subject(mock_get_db, client, clinician_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = {"id": 42}
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post(
        "/patients",
        headers=clinician_headers,
        json={
            "name": "Sample Patient",
            "dob": "1980-02-03",
            "gender": "F",
            "diagnosis": "Demo note",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["id"] == 42
    insert_query, insert_params = cursor.execute.call_args_list[0].args
    assert "RETURNING id" in insert_query
    assert insert_params[2:] == (
        "F",
        response.get_json()["mrn"],
        "Demo note",
        "clinician-sub",
    )
    assert any("INSERT INTO audit_events" in call.args[0] for call in cursor.execute.call_args_list)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"dob": "1980-02-03", "gender": "F"},
        {"name": "  ", "dob": "1980-02-03", "gender": "F"},
        {"name": "x" * 151, "dob": "1980-02-03", "gender": "F"},
        {"name": "Sample", "dob": "03-02-1980", "gender": "F"},
        {"name": "Sample", "dob": "1980-02-30", "gender": "F"},
        {"name": "Sample", "dob": "1980-02-03", "gender": "X"},
        {
            "name": "Sample",
            "dob": "1980-02-03",
            "gender": "F",
            "diagnosis": "x" * 256,
        },
    ],
)
def test_create_patient_rejects_invalid_input(client, clinician_headers, payload):
    response = client.post("/patients", headers=clinician_headers, json=payload)
    assert response.status_code == 400


@patch("app.routes.patients.get_db")
def test_patient_id_is_bound_as_query_parameter(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = FAKE_PATIENT
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients/1", headers=auth_headers)
    assert response.status_code == 200
    query, params = cursor.execute.call_args_list[0].args
    assert "WHERE id = %s" in query
    assert params == (1,)


def test_patient_id_injection_payload_is_rejected(client, auth_headers):
    response = client.get("/patients/1%20OR%201=1", headers=auth_headers)
    assert response.status_code == 404
