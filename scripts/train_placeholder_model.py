"""
Placeholder heart-disease model trainer.

Run this script ONCE to generate the placeholder model artifact:
    python scripts/train_placeholder_model.py

TODO: Replace this entire script with your real model training pipeline.
      The generated model (heart_disease_model.pkl) is trained on a tiny
      *synthetic* dataset and must never be used for clinical decisions.
"""
import os
import pickle

import numpy as np
from sklearn.ensemble import RandomForestClassifier

RANDOM_STATE = 42
N_SAMPLES = 200
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "model")
MODEL_PATH = os.path.join(MODEL_DIR, "heart_disease_model.pkl")

FEATURE_NAMES = [
    "age", "sex", "cp", "trestbps", "chol",
    "fbs", "restecg", "thalach", "exang",
    "oldpeak", "slope", "ca", "thal",
]


def generate_synthetic_data(n: int):
    rng = np.random.default_rng(RANDOM_STATE)
    X = rng.random((n, len(FEATURE_NAMES)))
    # Synthetic label: high risk when age_proxy + chol_proxy > threshold
    y = ((X[:, 0] + X[:, 4]) > 1.0).astype(int)
    return X, y


def train_and_save():
    os.makedirs(MODEL_DIR, exist_ok=True)
    X, y = generate_synthetic_data(N_SAMPLES)
    clf = RandomForestClassifier(n_estimators=10, random_state=RANDOM_STATE)
    clf.fit(X, y)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)
    print(f"[INFO] Placeholder model saved to: {MODEL_PATH}")
    print("[WARN] This model is SYNTHETIC and NOT suitable for clinical use.")
    print("[TODO] Replace with your real trained model.")


if __name__ == "__main__":
    train_and_save()
