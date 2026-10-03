"""
ml/train.py – MediGuard Heart Disease Model Training Pipeline
==============================================================
Downloads the UCI Cleveland Heart Disease dataset, trains three classifiers
(Logistic Regression, Random Forest, SVM) with stratified 5-fold cross-
validation, selects the best model by recall/ROC-AUC (because missing a sick
patient is more costly than a false alarm), evaluates on a held-out test set,
saves plots to ml/reports/, and persists the best pipeline to
ml/model/heart_model.joblib with accompanying ml/model/metadata.json.

Usage:
    python ml/train.py [--test-size 0.2] [--cv-folds 5] [--seed 42]

Requires: ucimlrepo, pandas, scikit-learn, matplotlib, seaborn, joblib
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")  # non-interactive backend (safe for servers / CI)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

warnings.filterwarnings("ignore")
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ── Directory constants ───────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "model"
REPORTS_DIR = ROOT / "reports"

FEATURE_NAMES = [
    "age", "sex", "cp", "trestbps", "chol",
    "fbs", "restecg", "thalach", "exang",
    "oldpeak", "slope", "ca", "thal",
]
TARGET_COL = "target"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_raw_data() -> pd.DataFrame:
    """
    Download the UCI Heart Disease (Cleveland) dataset using ucimlrepo.
    Falls back to a cached CSV in ml/data/ if the download fails (e.g. no network).
    Raises RuntimeError if neither source is available.
    """
    csv_cache = DATA_DIR / "heart_cleveland_raw.csv"

    # Try ucimlrepo first
    try:
        from ucimlrepo import fetch_ucirepo  # type: ignore
        log.info("Downloading dataset from UCI repository (id=45)…")
        ds = fetch_ucirepo(id=45)
        X = ds.data.features  # type: ignore[attr-defined]
        y = ds.data.targets   # type: ignore[attr-defined]
        df = pd.concat([X, y], axis=1)
        df.columns = [c.lower().strip() for c in df.columns]
        # Save a local cache
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_cache, index=False)
        log.info("Dataset saved to %s (%d rows)", csv_cache, len(df))
        return df
    except Exception as exc:
        log.warning("ucimlrepo download failed (%s). Trying local cache…", exc)

    # Try cached CSV
    if csv_cache.exists():
        log.info("Loading cached dataset from %s", csv_cache)
        return pd.read_csv(csv_cache)

    # Nothing worked → stop and instruct the user
    raise RuntimeError(
        "\n\n"
        "ERROR: Could not download or find the UCI Heart Disease dataset.\n"
        "Please download it manually:\n"
        "  URL: https://archive.ics.uci.edu/ml/machine-learning-databases/heart-disease/processed.cleveland.data\n"
        "  Save as: ml/data/heart_cleveland_raw.csv\n"
        "  Add a header row: age,sex,cp,trestbps,chol,fbs,restecg,thalach,exang,oldpeak,slope,ca,thal,num\n"
        "  Then re-run: python ml/train.py\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Preprocessing
# ─────────────────────────────────────────────────────────────────────────────

def preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Clean the raw dataframe:
    - Rename 'num' → 'target' if necessary, binarize (0 vs 1+)
    - Replace '?' with NaN, impute ca and thal with column mode
    - Ensure correct dtypes
    Returns (X, y) where X has exactly FEATURE_NAMES columns.
    """
    df = df.copy()

    # Normalise column names
    df.columns = [c.lower().strip() for c in df.columns]

    # Handle target column – UCI uses 'num', some mirrors use 'target'
    if "num" in df.columns and "target" not in df.columns:
        df = df.rename(columns={"num": "target"})

    # Binarize: 0 = no disease, 1 = disease (any severity 1-4)
    df["target"] = (df["target"] > 0).astype(int)

    # Replace '?' with NaN (raw Cleveland CSV uses '?' for missing values)
    df = df.replace("?", np.nan)

    # Convert all feature columns to numeric
    for col in FEATURE_NAMES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Impute missing values with column mode (ca and thal are the culprits)
    missing_cols = [c for c in FEATURE_NAMES if df[c].isna().any()]
    if missing_cols:
        log.info("Imputing missing values in: %s", missing_cols)
        for col in missing_cols:
            mode_val = df[col].mode()[0]
            df[col] = df[col].fillna(mode_val)
            log.info("  %s: imputed %d values with mode=%s",
                     col, df[col].isna().sum(), mode_val)

    # Check all feature columns present
    missing_feats = [f for f in FEATURE_NAMES if f not in df.columns]
    if missing_feats:
        raise ValueError(f"Missing expected feature columns: {missing_feats}")

    X = df[FEATURE_NAMES].astype(float)
    y = df[TARGET_COL]

    log.info("Dataset shape after preprocessing: X=%s, y distribution:\n%s",
             X.shape, y.value_counts().to_string())

    return X, y


# ─────────────────────────────────────────────────────────────────────────────
# 3. Model definitions
# ─────────────────────────────────────────────────────────────────────────────

def build_pipelines() -> dict[str, Pipeline]:
    """
    Return a dict of named sklearn Pipelines.
    Each pipeline: StandardScaler → Classifier.
    We scale all models for fair comparison (helps LR and SVM; neutral for RF).

    Model selection rationale:
    - Logistic Regression: fast, interpretable baseline; good probability calibration
    - Random Forest: handles non-linearity and feature interactions; robust
    - SVM (RBF kernel): strong in high-dimensional, small-N settings; good margin
    """
    return {
        "LogisticRegression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=1000,
                class_weight="balanced",  # handles class imbalance
                random_state=42,
                C=1.0,
            )),
        ]),
        "RandomForest": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=200,
                max_depth=None,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            )),
        ]),
        "SVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(
                kernel="rbf",
                C=1.0,
                probability=True,        # needed for predict_proba and ROC-AUC
                class_weight="balanced",
                random_state=42,
            )),
        ]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cross-validation
# ─────────────────────────────────────────────────────────────────────────────

def cross_validate_models(
    pipelines: dict[str, Pipeline],
    X: pd.DataFrame,
    y: pd.Series,
    cv_folds: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Run stratified k-fold CV on each pipeline.
    Reports accuracy, precision, recall, F1, and ROC-AUC.

    WHY RECALL IS THE PRIMARY METRIC:
    In a medical screening context, a False Negative (predicting 'no disease'
    when the patient actually has heart disease) is far more dangerous than a
    False Positive. A missed sick patient may go untreated; a false alarm
    triggers further clinical tests. We therefore optimise for recall and
    also track ROC-AUC as a threshold-independent measure.
    """
    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    scoring = ["accuracy", "precision", "recall", "f1", "roc_auc"]

    rows = []
    for name, pipeline in pipelines.items():
        log.info("Cross-validating %s (%d folds)…", name, cv_folds)
        cv_result = cross_validate(
            pipeline, X, y,
            cv=skf,
            scoring=scoring,
            return_train_score=False,
            n_jobs=-1,
        )
        row = {"model": name}
        for metric in scoring:
            scores = cv_result[f"test_{metric}"]
            row[f"{metric}_mean"] = scores.mean()
            row[f"{metric}_std"] = scores.std()
        rows.append(row)

    results = pd.DataFrame(rows).set_index("model")
    log.info("\nCV Results:\n%s", results.to_string())
    return results


def select_best_model(cv_results: pd.DataFrame) -> str:
    """
    Select the best model using a composite score: 0.6 * recall + 0.4 * roc_auc.
    Recall is weighted higher because missing a sick patient is costlier.
    """
    cv_results = cv_results.copy()
    cv_results["composite"] = (
        0.6 * cv_results["recall_mean"] + 0.4 * cv_results["roc_auc_mean"]
    )
    best = cv_results["composite"].idxmax()
    log.info("Best model by composite score (0.6*recall + 0.4*roc_auc): %s", best)
    return str(best)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Final evaluation on held-out test set
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_on_test(
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict[str, float]:
    """Compute metrics on the held-out test set."""
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    metrics: dict[str, float] = {
        "accuracy":  round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall":    round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1":        round(f1_score(y_test, y_pred, zero_division=0), 4),
        "roc_auc":   round(roc_auc_score(y_test, y_proba), 4),
    }
    log.info("Test-set metrics: %s", metrics)
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# 6. Plots
# ─────────────────────────────────────────────────────────────────────────────

def save_confusion_matrix(
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    model_name: str,
    out_dir: Path,
) -> None:
    """Save confusion-matrix heatmap to ml/reports/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    y_pred = pipeline.predict(X_test)
    cm = confusion_matrix(y_test, y_pred)
    fig, ax = plt.subplots(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=["No Disease", "Disease"])
    disp.plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(f"Confusion Matrix – {model_name}\n(held-out test set)")
    plt.tight_layout()
    path = out_dir / "confusion_matrix.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    log.info("Saved confusion matrix to %s", path)


def save_roc_curve(
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    model_name: str,
    out_dir: Path,
) -> None:
    """Save ROC curve plot to ml/reports/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    y_proba = pipeline.predict_proba(X_test)[:, 1]
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    auc = roc_auc_score(y_test, y_proba)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, lw=2, label=f"{model_name} (AUC = {auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="Random classifier")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate (Recall)")
    ax.set_title("ROC Curve – Held-out Test Set")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    path = out_dir / "roc_curve.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    log.info("Saved ROC curve to %s", path)


def save_cv_comparison(cv_results: pd.DataFrame, out_dir: Path) -> None:
    """Bar-chart comparing CV recall and ROC-AUC across models."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, metric in zip(axes, ["recall_mean", "roc_auc_mean"]):
        bars = ax.bar(cv_results.index, cv_results[metric], color=["#4C72B0", "#DD8452", "#55A868"])
        ax.set_ylim(0, 1)
        ax.set_title(metric.replace("_mean", "").upper() + " (5-fold CV mean)")
        ax.set_ylabel("Score")
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=10)
    plt.suptitle("Model Comparison – Cross-Validation", fontsize=13, fontweight="bold")
    plt.tight_layout()
    path = out_dir / "cv_comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    log.info("Saved CV comparison to %s", path)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Save artefacts
# ─────────────────────────────────────────────────────────────────────────────

def save_model_and_metadata(
    pipeline: Pipeline,
    model_name: str,
    test_metrics: dict[str, float],
    cv_results: pd.DataFrame,
    out_dir: Path,
) -> None:
    """Persist the fitted pipeline and a metadata JSON file."""
    import sklearn
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "heart_model.joblib"
    joblib.dump(pipeline, model_path)
    log.info("Saved model pipeline to %s", model_path)

    # CV metrics for the best model
    cv_row = cv_results.loc[model_name].to_dict()

    metadata: dict[str, Any] = {
        "model_type": model_name,
        "feature_names": FEATURE_NAMES,
        "target": {"0": "no heart disease", "1": "heart disease"},
        "training_date": datetime.now().isoformat(),
        "library_versions": {
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
        },
        "cv_metrics": {
            k: round(float(v), 4) for k, v in cv_row.items()
        },
        "test_metrics": test_metrics,
        "training_data": "UCI Heart Disease (Cleveland), 303 rows, ucimlrepo id=45",
        "disclaimer": (
            "This model is for EDUCATIONAL PURPOSES ONLY. "
            "It must NOT be used for real clinical decisions."
        ),
    }

    meta_path = out_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    log.info("Saved metadata to %s", meta_path)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Main entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main(test_size: float = 0.2, cv_folds: int = 5, seed: int = 42) -> None:
    log.info("=" * 60)
    log.info("MediGuard – Heart Disease Model Training")
    log.info("=" * 60)

    # Load and preprocess
    raw_df = load_raw_data()
    X, y = preprocess(raw_df)

    # Train/test split (stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y
    )
    log.info("Train: %d rows | Test: %d rows", len(X_train), len(X_test))

    # Cross-validate all models
    pipelines = build_pipelines()
    cv_results = cross_validate_models(pipelines, X_train, y_train, cv_folds, seed)

    # Save CV comparison plot
    save_cv_comparison(cv_results, REPORTS_DIR)

    # Select best model
    best_name = select_best_model(cv_results)

    # Refit best pipeline on full training set
    best_pipeline = pipelines[best_name]
    log.info("Fitting best model (%s) on full training set…", best_name)
    best_pipeline.fit(X_train, y_train)

    # Evaluate on held-out test set
    test_metrics = evaluate_on_test(best_pipeline, X_test, y_test)

    # Save plots
    save_confusion_matrix(best_pipeline, X_test, y_test, best_name, REPORTS_DIR)
    save_roc_curve(best_pipeline, X_test, y_test, best_name, REPORTS_DIR)

    # Save model + metadata
    save_model_and_metadata(best_pipeline, best_name, test_metrics, cv_results, MODEL_DIR)

    log.info("=" * 60)
    log.info("Training complete!")
    log.info("Best model : %s", best_name)
    log.info("Test recall : %.4f (higher = fewer missed sick patients)", test_metrics["recall"])
    log.info("Test ROC-AUC: %.4f", test_metrics["roc_auc"])
    log.info("Model saved : %s", MODEL_DIR / "heart_model.joblib")
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train MediGuard heart-disease model")
    parser.add_argument("--test-size", type=float, default=0.2,
                        help="Fraction of data to hold out for testing (default 0.2)")
    parser.add_argument("--cv-folds", type=int, default=5,
                        help="Number of stratified CV folds (default 5)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default 42)")
    args = parser.parse_args()
    main(test_size=args.test_size, cv_folds=args.cv_folds, seed=args.seed)
