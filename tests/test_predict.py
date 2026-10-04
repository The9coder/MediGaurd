"""Tests for POST /predict and the production model fail-closed gate."""

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
    assert client.post("/predict", json=VALID_PAYLOAD).status_code == 401


@patch("app.routes.predict.get_db")
def test_predict_success(mock_get_db, client, auth_headers):
    mock_get_db.return_value.cursor.return_value = MagicMock()
    response = client.post("/predict", json=VALID_PAYLOAD, headers=auth_headers)
    assert response.status_code == 200
    result = response.get_json()
    assert result["prediction"] in (0, 1)
    assert "risk_probability" in result
    assert result["risk_label"] in ("HIGH", "LOW")
    assert "disclaimer" in result


@patch("app.routes.predict.get_db")
def test_predict_audits_without_persisting_features(mock_get_db, client, auth_headers):
    cursor = MagicMock()
    mock_get_db.return_value.cursor.return_value = cursor

    response = client.post("/predict", json=VALID_PAYLOAD, headers=auth_headers)

    assert response.status_code == 200
    calls = cursor.execute.call_args_list
    assert any("INSERT INTO audit_events" in call.args[0] for call in calls)
    assert not any("prediction_history" in call.args[0] for call in calls)


def test_predict_missing_features(client, auth_headers):
    incomplete = {key: value for key, value in VALID_PAYLOAD.items() if key != "age"}
    response = client.post("/predict", json=incomplete, headers=auth_headers)
    assert response.status_code == 400
    assert "Input validation failed" in response.get_json()["error"]


def test_predict_rejects_non_object_json(client, auth_headers):
    response = client.post("/predict", json=["invalid"], headers=auth_headers)
    assert response.status_code == 400
    assert response.get_json()["error"] == "Request body must be a JSON object"


def test_predict_without_oidc_session_is_unauthorized(client):
    response = client.post("/predict", json=VALID_PAYLOAD)
    assert response.status_code == 401


def test_production_predictions_fail_closed_until_enabled(client, app, auth_headers):
    app.config["DEPLOYMENT_ENV"] = "production"
    app.config["ENABLE_PREDICTIONS"] = False
    response = client.post("/predict", json=VALID_PAYLOAD, headers=auth_headers)
    assert response.status_code == 503
