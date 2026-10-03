"""
Tests for GET /patients/<id>

The DB is not running during unit tests, so we mock the database layer.
"""
from unittest.mock import MagicMock, patch


FAKE_PATIENT = {
    "id": 1,
    "name": "Jane Doe",
    "dob": "1975-03-12",
    "gender": "F",
    "mrn": "MRN-000001",
    "diagnosis": "Hypertension, Stage 1",
    "assigned_to": "clinician",
}


@patch("app.routes.patients.get_db")
def test_get_patient_success(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = FAKE_PATIENT
    mock_get_db.return_value.cursor.return_value = cursor

    resp = client.get("/patients/1", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mrn"] == "MRN-000001"
    assert data["name"] == "Jane Doe"


@patch("app.routes.patients.get_db")
def test_get_patient_not_found(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    mock_get_db.return_value.cursor.return_value = cursor

    resp = client.get("/patients/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_get_patient_requires_auth(client):
    resp = client.get("/patients/1")
    assert resp.status_code == 401


@patch("app.routes.patients.get_db")
def test_patient_list_is_scoped_to_clinician(mock_get_db, client):
    cursor = MagicMock()
    cursor.fetchall.return_value = [FAKE_PATIENT]
    mock_get_db.return_value.cursor.return_value = cursor
    login = client.post(
        "/login", json={"username": "clinician", "password": "clinic456"}
    )
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}

    response = client.get("/patients", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["patients"] == [FAKE_PATIENT]
    query, params = cursor.execute.call_args.args
    assert "WHERE assigned_to = %s" in query
    assert params == ("clinician",)


@patch("app.routes.patients.get_db")
def test_create_patient_assigns_record_to_signed_in_user(mock_get_db, client):
    cursor = MagicMock()
    cursor.lastrowid = 42
    mock_get_db.return_value.cursor.return_value = cursor
    login = client.post(
        "/login", json={"username": "clinician", "password": "clinic456"}
    )

    response = client.post(
        "/patients",
        headers={"Authorization": f"Bearer {login.get_json()['token']}"},
        json={
            "name": "Sample Patient",
            "dob": "1980-02-03",
            "gender": "F",
            "diagnosis": "Demo note",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["id"] == 42
    assert cursor.execute.call_args.args[1][2:] == (
        "F",
        response.get_json()["mrn"],
        "Demo note",
        "clinician",
    )


@patch("app.routes.patients.get_db")
def test_patient_id_is_interpolated_into_query(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    cursor.fetchone.return_value = FAKE_PATIENT
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.get("/patients/1%20OR%201=1", headers=auth_headers)

    assert response.status_code == 200
    query, params = cursor.execute.call_args.args
    assert "WHERE id = 1 OR 1=1" in query
    assert params == ()
