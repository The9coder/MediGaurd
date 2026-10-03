"""
Tests for POST /predict
"""
from unittest.mock import MagicMock, patch

VALID_PAYLOAD = {
    "age": 55.0,
    "sex": 1.0,
    "cp": 3.0,
    "trestbps": 140.0,
    "chol": 250.0,
    "fbs": 0.0,
    "restecg": 1.0,
    "thalach": 150.0,
    "exang": 0.0,
    "oldpeak": 1.5,
    "slope": 2.0,
    "ca": 0.0,
    "thal": 3.0,
}


def test_predict_requires_auth(client):
    resp = client.post("/predict", json=VALID_PAYLOAD)
    assert resp.status_code == 401


@patch("app.routes.predict.get_db")
def test_predict_success(mock_get_db, client, auth_headers):
    mock_get_db.return_value.cursor.return_value = MagicMock()
    resp = client.post("/predict", json=VALID_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "prediction" in data
    assert data["prediction"] in (0, 1)
    assert "risk_probability" in data
    assert data["risk_label"] in ("HIGH", "LOW")
    assert "disclaimer" in data


@patch("app.routes.predict.get_db")
def test_predict_saves_history_for_signed_in_user(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post("/predict", json=VALID_PAYLOAD, headers=auth_headers)

    assert response.status_code == 200
    insert_call = next(
        call for call in cursor.execute.call_args_list
        if "INSERT INTO prediction_history" in call.args[0]
    )
    assert insert_call.args[1][0] == "admin"


def test_predict_missing_features(client, auth_headers):
    incomplete = {k: v for k, v in VALID_PAYLOAD.items() if k != "age"}
    resp = client.post("/predict", json=incomplete, headers=auth_headers)
    assert resp.status_code == 400
    assert "Input validation failed" in resp.get_json()["error"]


def test_predict_invalid_token(client):
    resp = client.post(
        "/predict",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer totally-invalid-token"},
    )
    assert resp.status_code == 401


def test_predict_expired_token(client, app):
    """Simulate an expired token by temporarily reducing expiry to 0 hours."""
    import jwt as pyjwt
    import datetime

    payload = {
        "sub": "admin",
        "role": "admin",
        "iat": datetime.datetime.utcnow() - datetime.timedelta(hours=2),
        "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=1),
    }
    expired_token = pyjwt.encode(payload, app.config["JWT_SECRET"], algorithm="HS256")
    resp = client.post(
        "/predict",
        json=VALID_PAYLOAD,
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert "expired" in resp.get_json()["error"].lower()
