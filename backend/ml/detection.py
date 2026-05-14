"""
Detection model — RandomForest + XGBoost ensemble.

Designed for CICIDS2017 and UNSW-NB15 datasets. Feature engineering is
dataset-agnostic: any numeric columns become features, any 'Label'/'label'/'attack_cat'
column is the target (binary: benign vs attack).

Training script: backend/scripts/train_detection.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.core.config import settings
from backend.core.logging import logger

LABEL_CANDIDATES = ["Label", "label", "attack_cat", "Attack", "class"]
BENIGN_TOKENS = {"benign", "normal", "0"}


@dataclass
class DetectionArtifacts:
    rf: RandomForestClassifier
    xgb: XGBClassifier
    scaler: StandardScaler
    feature_cols: list[str]


# ------------------- preprocessing -------------------
def _find_label_col(df: pd.DataFrame) -> Optional[str]:
    for c in LABEL_CANDIDATES:
        if c in df.columns:
            return c
    # fallback: any column ending with 'label'
    for c in df.columns:
        if c.lower().endswith("label"):
            return c
    return None


def _binarise(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().apply(
        lambda v: 0 if v in BENIGN_TOKENS else 1
    )


def preprocess(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, list[str]]:
    """Clean dataset → X, y, feature_names."""
    # normalise column names (CICIDS has leading spaces)
    df.columns = [c.strip() for c in df.columns]

    label_col = _find_label_col(df)
    if label_col is None:
        raise ValueError(
            f"No label column found. Expected one of {LABEL_CANDIDATES}"
        )

    y = _binarise(df[label_col])
    X = df.drop(columns=[label_col])

    # drop obvious non-features
    drop_like = [
        "Flow ID", "Source IP", "Destination IP", "Timestamp",
        "src_ip", "dst_ip", "id", "srcip", "dstip",
    ]
    X = X.drop(columns=[c for c in drop_like if c in X.columns], errors="ignore")

    # keep numeric only
    X = X.select_dtypes(include=[np.number])

    # handle infinities / nans
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

    return X, y, X.columns.tolist()


# ------------------- training -------------------
def train(
    df: pd.DataFrame, save_dir: Optional[str] = None, test_size: float = 0.2
) -> dict:
    X, y, feats = preprocess(df)
    logger.info(f"Dataset shape after preprocess: {X.shape}, positives={y.sum()}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    logger.info("Training RandomForest...")
    rf = RandomForestClassifier(
        n_estimators=100, max_depth=20, n_jobs=-1, class_weight="balanced",
        random_state=42,
    )
    rf.fit(X_train_s, y_train)

    logger.info("Training XGBoost...")
    xgb = XGBClassifier(
        n_estimators=200, max_depth=8, learning_rate=0.1, n_jobs=-1,
        use_label_encoder=False, eval_metric="logloss", random_state=42,
    )
    xgb.fit(X_train_s, y_train)

    # Ensemble predictions
    rf_proba = rf.predict_proba(X_test_s)[:, 1]
    xgb_proba = xgb.predict_proba(X_test_s)[:, 1]
    ens_proba = (rf_proba + xgb_proba) / 2
    ens_pred = (ens_proba >= 0.5).astype(int)

    metrics = {
        "accuracy": float(accuracy_score(y_test, ens_pred)),
        "f1": float(f1_score(y_test, ens_pred)),
        "roc_auc": float(roc_auc_score(y_test, ens_proba)),
        "confusion_matrix": confusion_matrix(y_test, ens_pred).tolist(),
        "classification_report": classification_report(
            y_test, ens_pred, output_dict=True
        ),
    }
    logger.info(
        f"Ensemble: acc={metrics['accuracy']:.4f} "
        f"f1={metrics['f1']:.4f} auc={metrics['roc_auc']:.4f}"
    )

    if save_dir:
        save(rf, xgb, scaler, feats, save_dir)

    return metrics


# ------------------- persistence -------------------
def save(
    rf: RandomForestClassifier,
    xgb: XGBClassifier,
    scaler: StandardScaler,
    feats: list[str],
    save_dir: str,
) -> None:
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    joblib.dump(rf, Path(save_dir) / "detection_rf.pkl")
    joblib.dump(xgb, Path(save_dir) / "detection_xgb.pkl")
    joblib.dump(scaler, Path(save_dir) / "detection_scaler.pkl")
    joblib.dump(feats, Path(save_dir) / "detection_features.pkl")
    logger.info(f"Detection artifacts saved to {save_dir}")


def load(model_dir: Optional[str] = None) -> Optional[DetectionArtifacts]:
    d = Path(model_dir or settings.model_dir)
    try:
        rf = joblib.load(d / "detection_rf.pkl")
        xgb = joblib.load(d / "detection_xgb.pkl")
        scaler = joblib.load(d / "detection_scaler.pkl")
        feats = joblib.load(d / "detection_features.pkl")
        return DetectionArtifacts(rf=rf, xgb=xgb, scaler=scaler, feature_cols=feats)
    except FileNotFoundError:
        logger.warning(f"No detection artifacts found in {d}")
        return None


# ------------------- inference -------------------
def predict_proba(
    features: dict[str, float], artifacts: Optional[DetectionArtifacts] = None
) -> float:
    """Return P(attack) for a single event. Missing features default to 0."""
    artifacts = artifacts or load()
    if artifacts is None:
        # deterministic heuristic fallback when no trained model is available
        return min(1.0, sum(abs(float(v)) for v in features.values()) / 1000.0)

    x = np.array(
        [[features.get(c, 0.0) for c in artifacts.feature_cols]], dtype=float
    )
    x = artifacts.scaler.transform(x)
    p = (
        artifacts.rf.predict_proba(x)[:, 1][0]
        + artifacts.xgb.predict_proba(x)[:, 1][0]
    ) / 2
    return float(p)
