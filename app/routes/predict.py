"""
app/routes/predict.py – POST /predict
======================================
OIDC-session-protected endpoint that accepts 13 clinical features,
validates them (type + range), runs them through the trained
sklearn Pipeline, and returns risk probability + label + disclaimer.

Uses ml/model/heart_model.joblib (Logistic Regression pipeline
trained on the UCI Cleveland Heart Disease dataset).
"""

from __future__ import annotations

import hmac
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from flask import Blueprint, current_app, jsonify, request
from psycopg import Error as DatabaseError

from app.auth import auth_required
from app.database import get_db, write_audit

predict_bp = Blueprint("predict", __name__)

# ── Feature definitions with validation ranges ────────────────────────────────
# Each entry: (type, min, max, description)
FEATURE_SPEC: dict[str, tuple[type, float, float, str]] = {
    "age":      (float, 1,   120,  "Age in years"),
    "sex":      (float, 0,   1,    "Sex (0=female, 1=male)"),
    "cp":       (float, 1,   4,    "Chest pain type (1–4)"),
    "trestbps": (float, 60,  250,  "Resting blood pressure (mmHg)"),
    "chol":     (float, 100, 600,  "Serum cholesterol (mg/dl)"),
    "fbs":      (float, 0,   1,    "Fasting blood sugar > 120 mg/dl (0 or 1)"),
    "restecg":  (float, 0,   2,    "Resting ECG (0–2)"),
    "thalach":  (float, 60,  220,  "Max heart rate achieved"),
    "exang":    (float, 0,   1,    "Exercise-induced angina (0 or 1)"),
    "oldpeak":  (float, 0.0, 10.0, "ST depression (exercise vs rest)"),
    "slope":    (float, 1,   3,    "Slope of peak exercise ST (1–3)"),
    "ca":       (float, 0,   3,    "Major vessels coloured by fluoroscopy (0–3)"),
    "thal":     (float, 3,   7,    "Thalassemia type (3, 6, or 7)"),
}

FEATURE_NAMES = list(FEATURE_SPEC.keys())

# ── Model loader (cached per process) ────────────────────────────────────────
_model: Any = None


def _get_model() -> Any:
    """Load and cache the trained sklearn pipeline from disk."""
    global _model
    if _model is None:
        model_path = Path(current_app.config.get("MODEL_PATH", "ml/model/heart_model.joblib"))
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. "
                "Run: python ml/train.py"
            )
        if current_app.config.get("DEPLOYMENT_ENV") == "production":
            import hashlib

            expected_hash = current_app.config.get("MODEL_SHA256", "").lower()
            actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
            if not expected_hash or not hmac.compare_digest(actual_hash, expected_hash):
                raise RuntimeError("Prediction model integrity check failed")
        _model = joblib.load(model_path)
        current_app.logger.info("Loaded model from %s", model_path)
    return _model


def _validate_features(data: dict) -> tuple[list[float] | None, list[str]]:
    """
    Validate incoming JSON body against FEATURE_SPEC.
    Returns (feature_vector, []) on success or (None, [error_messages]) on failure.
    """
    errors: list[str] = []
    vector: list[float] = []

    unexpected = sorted(set(data) - set(FEATURE_SPEC))
    if unexpected:
        errors.append("Unexpected features: " + ", ".join(unexpected))

    for name, (dtype, lo, hi, desc) in FEATURE_SPEC.items():
        if name not in data:
            errors.append(f"Missing feature: '{name}' ({desc})")
            continue
        raw = data[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            errors.append(f"'{name}' must be a JSON number")
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            errors.append(f"'{name}' must be numeric")
            continue
        if not math.isfinite(val) or not (lo <= val <= hi):
            errors.append(f"'{name}' out of range [{lo}, {hi}], got: {val}")
            continue
        vector.append(val)

    if errors:
        return None, errors
    return vector, []


@predict_bp.route("/predict", methods=["POST"])
@auth_required
def predict() -> tuple[Any, int]:
    """
    POST /predict
    Body (JSON): { "age": 55, "sex": 1, ..., "thal": 3 }
    Returns: { prediction, risk_probability, risk_label, disclaimer }
    """
    data = request.get_json(silent=True)
    production_predictions_disabled = (
        current_app.config.get("DEPLOYMENT_ENV") == "production"
        and not current_app.config["ENABLE_PREDICTIONS"]
    )
    if production_predictions_disabled:
        return jsonify({
            "error": "Prediction service has not been approved for this deployment"
        }), 503
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    # Input validation
    feature_vector, errors = _validate_features(data)
    if errors:
        return jsonify({"error": "Input validation failed", "details": errors}), 400

    try:
        model = _get_model()
        X = np.array([feature_vector])
        prediction: int = int(model.predict(X)[0])
        probability: float = float(model.predict_proba(X)[0][1])
    except (FileNotFoundError, RuntimeError, OSError, ImportError):
        current_app.logger.error("Prediction model is unavailable or failed integrity validation")
        return jsonify({"error": "Prediction service is temporarily unavailable"}), 503
    except (ValueError, TypeError, IndexError, AttributeError) as error:
        current_app.logger.error("Prediction failed (%s)", type(error).__name__)
        return jsonify({"error": "Prediction service temporarily unavailable"}), 500

    if prediction not in (0, 1) or not math.isfinite(probability) or not 0 <= probability <= 1:
        current_app.logger.error("Prediction model returned an invalid result")
        return jsonify({"error": "Prediction service temporarily unavailable"}), 500

    risk_label = "HIGH" if prediction == 1 else "LOW"
    risk_probability = round(probability, 4)

    db = get_db()
    cursor = db.cursor()
    try:
        write_audit(cursor, "prediction.request", "prediction")
        db.commit()
    except DatabaseError:
        db.rollback()
        current_app.logger.exception("Prediction request audit event could not be saved")
        return jsonify({"error": "Prediction service is temporarily unavailable"}), 503
    finally:
        cursor.close()

    return jsonify({
        "prediction": prediction,
        "risk_probability": risk_probability,
        "risk_label": risk_label,
        "disclaimer": (
            "⚠️ FOR EDUCATIONAL / PORTFOLIO USE ONLY. "
            "This output is NOT a medical diagnosis and must NOT be used "
            "for clinical decision-making. Consult a qualified clinician."
        ),
    }), 200
