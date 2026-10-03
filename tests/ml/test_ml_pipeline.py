"""
tests/ml/test_ml_pipeline.py – pytest tests for the ML training pipeline

Tests verify:
  1. Data loading (real or cached CSV)
  2. Preprocessing shape and target binarization
  3. Pipeline prediction shape
  4. Saved model artifact loads and predicts correctly
  5. Metadata JSON has required fields
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

ML_DIR = ROOT / "ml"
MODEL_PATH = ML_DIR / "model" / "heart_model.joblib"
META_PATH = ML_DIR / "model" / "metadata.json"
DATA_DIR = ML_DIR / "data"

FEATURE_NAMES = [
    "age", "sex", "cp", "trestbps", "chol",
    "fbs", "restecg", "thalach", "exang",
    "oldpeak", "slope", "ca", "thal",
]

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def raw_df():
    """Load raw dataset (uses cached CSV so tests work offline)."""
    sys.path.insert(0, str(ML_DIR.parent))
    from ml.train import load_raw_data
    return load_raw_data()


@pytest.fixture(scope="session")
def preprocessed(raw_df):
    """Return (X, y) from the preprocessing step."""
    from ml.train import preprocess
    return preprocess(raw_df)


@pytest.fixture(scope="session")
def loaded_model():
    """Load the saved joblib model (skips if not built yet)."""
    if not MODEL_PATH.exists():
        pytest.skip(f"Model artifact not found at {MODEL_PATH}. Run: python ml/train.py")
    import joblib
    return joblib.load(MODEL_PATH)


@pytest.fixture(scope="session")
def metadata():
    """Load metadata.json (skips if not built yet)."""
    if not META_PATH.exists():
        pytest.skip(f"Metadata not found at {META_PATH}. Run: python ml/train.py")
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Tests: Data loading ───────────────────────────────────────────────────────

class TestDataLoading:

    def test_raw_df_not_empty(self, raw_df):
        """Dataset must have rows."""
        assert len(raw_df) > 0, "Dataset is empty"

    def test_raw_df_has_expected_columns(self, raw_df):
        """At least the 13 feature columns must be present."""
        cols = [c.lower() for c in raw_df.columns]
        for feat in FEATURE_NAMES:
            assert feat in cols, f"Missing feature column: {feat}"

    def test_raw_df_row_count(self, raw_df):
        """Cleveland subset should have ~303 rows."""
        assert 290 <= len(raw_df) <= 310, (
            f"Expected ~303 rows, got {len(raw_df)}"
        )


# ── Tests: Preprocessing ─────────────────────────────────────────────────────

class TestPreprocessing:

    def test_X_shape(self, preprocessed):
        X, y = preprocessed
        assert X.shape[1] == 13, f"Expected 13 features, got {X.shape[1]}"

    def test_no_missing_values(self, preprocessed):
        X, y = preprocessed
        assert X.isna().sum().sum() == 0, "X still has NaN values after preprocessing"

    def test_target_binary(self, preprocessed):
        """Target must only contain 0 and 1 after binarization."""
        _, y = preprocessed
        unique = set(y.unique())
        assert unique <= {0, 1}, f"Target has unexpected values: {unique}"

    def test_target_both_classes_present(self, preprocessed):
        """Both classes must be present (no single-class dataset)."""
        _, y = preprocessed
        assert 0 in y.values and 1 in y.values

    def test_X_numeric(self, preprocessed):
        """All features must be numeric (float or int)."""
        X, _ = preprocessed
        for col in X.columns:
            assert np.issubdtype(X[col].dtype, np.number), (
                f"Column {col} is not numeric: {X[col].dtype}"
            )


# ── Tests: Saved model artifact ──────────────────────────────────────────────

class TestSavedModel:

    def test_model_loads(self, loaded_model):
        """Model must load without error."""
        assert loaded_model is not None

    def test_model_has_predict(self, loaded_model):
        assert hasattr(loaded_model, "predict")

    def test_model_has_predict_proba(self, loaded_model):
        assert hasattr(loaded_model, "predict_proba")

    def test_prediction_shape(self, loaded_model):
        """Single-row prediction must return shape (1,)."""
        sample = np.array([[63, 1, 1, 145, 233, 1, 2, 150, 0, 2.3, 3, 0, 6]])
        pred = loaded_model.predict(sample)
        assert pred.shape == (1,), f"Unexpected prediction shape: {pred.shape}"

    def test_prediction_is_binary(self, loaded_model):
        """Predictions must be 0 or 1."""
        sample = np.array([[63, 1, 1, 145, 233, 1, 2, 150, 0, 2.3, 3, 0, 6]])
        pred = loaded_model.predict(sample)
        assert pred[0] in (0, 1), f"Prediction {pred[0]} is not binary"

    def test_proba_shape(self, loaded_model):
        """predict_proba must return shape (n, 2)."""
        sample = np.array([[63, 1, 1, 145, 233, 1, 2, 150, 0, 2.3, 3, 0, 6]])
        proba = loaded_model.predict_proba(sample)
        assert proba.shape == (1, 2), f"Unexpected proba shape: {proba.shape}"

    def test_proba_sums_to_one(self, loaded_model):
        """Probabilities for each row must sum to ~1."""
        samples = np.random.default_rng(42).random((10, 13))
        probas = loaded_model.predict_proba(samples)
        row_sums = probas.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_batch_prediction(self, loaded_model, preprocessed):
        """Model must handle a batch of inputs."""
        X, _ = preprocessed
        preds = loaded_model.predict(X.values[:20])
        assert preds.shape == (20,)


# ── Tests: Metadata JSON ──────────────────────────────────────────────────────

class TestMetadata:

    REQUIRED_KEYS = [
        "model_type", "feature_names", "target",
        "training_date", "library_versions",
        "cv_metrics", "test_metrics", "disclaimer",
    ]

    def test_required_keys_present(self, metadata):
        for key in self.REQUIRED_KEYS:
            assert key in metadata, f"Missing metadata key: {key}"

    def test_feature_names_correct(self, metadata):
        assert metadata["feature_names"] == FEATURE_NAMES

    def test_test_metrics_have_recall(self, metadata):
        assert "recall" in metadata["test_metrics"]

    def test_test_metrics_recall_reasonable(self, metadata):
        """Recall should be above 0.5 for a functioning model."""
        recall = metadata["test_metrics"]["recall"]
        assert recall > 0.5, f"Recall too low: {recall}. Check training."

    def test_test_metrics_roc_auc_reasonable(self, metadata):
        """ROC-AUC should be better than random (> 0.5)."""
        roc_auc = metadata["test_metrics"]["roc_auc"]
        assert roc_auc > 0.5, f"ROC-AUC too low: {roc_auc}. Model may be broken."

    def test_disclaimer_present(self, metadata):
        assert len(metadata["disclaimer"]) > 0
