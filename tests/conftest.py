"""Shared pytest fixtures for MediGuard tests."""

import os
import pickle
import sys

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(scope="session")
def placeholder_model(tmp_path_factory):
    """Train a deterministic model for isolated prediction-route tests."""
    model_dir = tmp_path_factory.mktemp("model")
    model_path = str(model_dir / "heart_disease_model.pkl")
    rng = np.random.default_rng(42)
    features = rng.random((100, 13))
    target = (features[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=5, random_state=42)
    model.fit(features, target)
    with open(model_path, "wb") as model_file:
        pickle.dump(model, model_file)
    return model_path


@pytest.fixture()
def app(placeholder_model):
    """Create a test app with no live identity provider or database."""
    from app.factory import create_app

    application = create_app("development")
    application.config.update(
        {
            "TESTING": True,
            "RATELIMIT_ENABLED": False,
            "MODEL_PATH": placeholder_model,
            "ENABLE_PREDICTIONS": True,
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_headers(client):
    """Create an authenticated administrator session for route tests."""
    with client.session_transaction() as session:
        session["principal"] = {"sub": "admin-sub", "role": "admin"}
        session["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}


@pytest.fixture()
def clinician_headers(client):
    """Create an authenticated clinician session for route tests."""
    with client.session_transaction() as session:
        session["principal"] = {"sub": "clinician-sub", "role": "clinician"}
        session["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}
