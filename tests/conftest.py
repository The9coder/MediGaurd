"""
Shared pytest fixtures for MediGuard tests.
"""
import os
import pickle
import sys

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

# ── Make sure the project root is on the path ────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(scope="session")
def placeholder_model(tmp_path_factory):
    """
    Train and persist a tiny placeholder model so /predict tests don't fail
    due to a missing model file.
    """
    model_dir = tmp_path_factory.mktemp("model")
    model_path = str(model_dir / "heart_disease_model.pkl")

    rng = np.random.default_rng(42)
    X = rng.random((100, 13))
    y = (X[:, 0] > 0.5).astype(int)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)
    with open(model_path, "wb") as f:
        pickle.dump(clf, f)

    return model_path


@pytest.fixture()
def app(placeholder_model):
    """Create a Flask test application with in-memory / mocked DB."""
    os.environ["FLASK_ENV"] = "testing"

    from app.factory import create_app

    application = create_app("development")
    application.config.update(
        {
            "TESTING": True,
            "MODEL_PATH": placeholder_model,
            "DEMO_ADMIN_PASSWORD": "test-admin-password",
            "DEMO_CLINICIAN_PASSWORD": "test-clinician-password",
            # Point DB to a non-existent host so DB tests are mocked
            "DB_HOST": "localhost",
            "DB_PORT": "9999",
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(client):
    """Return a valid JWT Authorization header for the admin user."""
    resp = client.post(
        "/login",
        json={"username": "admin", "password": "test-admin-password"},
        content_type="application/json",
    )
    token = resp.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}
