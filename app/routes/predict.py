"""
app/routes/predict.py – POST /predict
======================================
JWT-protected endpoint that accepts 13 clinical features,
validates them (type + range), runs them through the trained
sklearn Pipeline, and returns risk probability + label + disclaimer.

Uses ml/model/heart_model.joblib (Logistic Regression pipeline
trained on the UCI Cleveland Heart Disease dataset).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from flask import Blueprint, current_app, jsonify, request
from mysql.connector import Error as MySQLError

from app.auth import jwt_required
from app.database import ensure_app_tables, get_db

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

    for name, (dtype, lo, hi, desc) in FEATURE_SPEC.items():
        if name not in data:
            errors.append(f"Missing feature: '{name}' ({desc})")
            continue
        raw = data[name]
        try:
            val = float(raw)
        except (TypeError, ValueError):
            errors.append(f"'{name}' must be numeric, got: {raw!r}")
            continue
        if not (lo <= val <= hi):
            errors.append(f"'{name}' out of range [{lo}, {hi}], got: {val}")
            continue
        vector.append(val)

    if errors:
        return None, errors
    return vector, []


@predict_bp.route("/predict", methods=["POST"])
@jwt_required
def predict() -> tuple[Any, int]:
    """
    POST /predict
    Body (JSON): { "age": 55, "sex": 1, ..., "thal": 3 }
    Returns: { prediction, risk_probability, risk_label, disclaimer }
    """
    data: dict = request.get_json(silent=True) or {}

    # Input validation
    feature_vector, errors = _validate_features(data)
    if errors:
        return jsonify({"error": "Input validation failed", "details": errors}), 400

    try:
        model = _get_model()
        X = np.array([feature_vector])
        prediction: int = int(model.predict(X)[0])
        probability: float = float(model.predict_proba(X)[0][1])
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        current_app.logger.exception("Prediction error")
        return jsonify({"error": "Prediction service temporarily unavailable"}), 500

    risk_label = "HIGH" if prediction == 1 else "LOW"
    risk_probability = round(probability, 4)

    db = get_db()
    cursor = db.cursor()
    try:
        ensure_app_tables(cursor)
        cursor.execute(
            "INSERT INTO prediction_history "
            "(username, features, prediction, risk_probability, risk_label) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                request.jwt_payload["sub"],
                json.dumps(data),
                prediction,
                risk_probability,
                risk_label,
            ),
        )
        db.commit()
    except MySQLError:
        db.rollback()
        current_app.logger.exception("Prediction history could not be saved")
        return jsonify({"error": "Prediction history service is temporarily unavailable"}), 503
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


@predict_bp.route("/predictions", methods=["GET"])
@jwt_required
def prediction_history():
    username = request.jwt_payload["sub"]
    is_admin = request.jwt_payload.get("role") == "admin"
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        ensure_app_tables(cursor)
        if is_admin:
            cursor.execute(
                "SELECT id, username, features, prediction, risk_probability, "
                "risk_label, created_at FROM prediction_history ORDER BY id DESC"
            )
        else:
            cursor.execute(
                "SELECT id, username, features, prediction, risk_probability, "
                "risk_label, created_at FROM prediction_history "
                "WHERE username = %s ORDER BY id DESC",
                (username,),
            )
        records = cursor.fetchall()
    except MySQLError:
        current_app.logger.exception("Prediction history query failed")
        return jsonify({"error": "Prediction history is temporarily unavailable"}), 503
    finally:
        cursor.close()

    return jsonify({"predictions": records}), 200
