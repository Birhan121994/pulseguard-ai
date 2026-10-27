
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score


MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODEL_DIR / "failure_predictor.json"

# Global system-wide features.
FEATURE_COLS = [
    "total_logs",
    "error_count",
    "warn_count",
    "error_rate",
    "unique_templates",
    "unique_services",
    "max_template_freq",
    "template_entropy",
]

# Features specific to each service and window.
SERVICE_FEATURE_COLS = [
    "service_log_count",
    "service_error_count",
    "service_warn_count",
]

# This list is stored in the model metadata.
# The numeric service ID is appended separately.
ALL_FEATURE_COLS = FEATURE_COLS + SERVICE_FEATURE_COLS

MODEL_VERSION = "3"
NUM_BOOST_ROUNDS = 100


def _service_mapping(services: list[str]) -> dict[str, int]:
    """Create deterministic service IDs."""
    return {
        service: index
        for index, service in enumerate(sorted(set(services)))
    }


def _model_params() -> dict:
    return {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "max_depth": 4,
        "eta": 0.1,
        "seed": 42,
        "nthread": -1,
    }


def _validate_global_features(
    features_df: pd.DataFrame,
) -> list[str]:
    return [
        column
        for column in FEATURE_COLS
        if column not in features_df.columns
    ]


def _build_service_matrix(
    features_df: pd.DataFrame,
    service_df: pd.DataFrame,
    service_id: int,
) -> np.ndarray:
    """
    Construct model inputs in the exact same order used during training:
    global features, service features, service ID.
    """
    missing_global = _validate_global_features(features_df)

    if missing_global:
        raise ValueError(
            f"Missing global feature columns: {missing_global}"
        )

    missing_service = [
        column
        for column in SERVICE_FEATURE_COLS
        if column not in service_df.columns
    ]

    if missing_service:
        raise ValueError(
            f"Missing service feature columns: {missing_service}"
        )

    if not features_df.index.equals(service_df.index):
        raise ValueError(
            "Global and service feature timestamps do not match"
        )

    global_values = features_df[FEATURE_COLS].to_numpy(dtype=float)

    service_values = service_df[
        SERVICE_FEATURE_COLS
    ].to_numpy(dtype=float)

    return np.column_stack([
        global_values,
        service_values,
        np.full(len(features_df), float(service_id)),
    ])


def train_failure_model(
    features_df: pd.DataFrame,
    label_matrix: dict[str, list[int]],
    services: list[str],
    service_features: dict[str, pd.DataFrame],
) -> dict:
    """Train and save a service-level XGBoost failure model."""
    if features_df.empty:
        return {
            "status": "insufficient_data",
            "message": "No feature windows available for training",
        }

    missing = _validate_global_features(features_df)

    if missing:
        return {
            "status": "error",
            "message": f"Missing feature columns: {missing}",
        }

    if not services:
        return {
            "status": "insufficient_data",
            "message": "No services found in the training data",
        }

    service_ids = _service_mapping(services)

    rows = []
    labels = []

    for service in sorted(set(services)):
        if service not in label_matrix:
            return {
                "status": "error",
                "message": f"Missing labels for service: {service}",
            }

        if service not in service_features:
            return {
                "status": "error",
                "message": f"Missing features for service: {service}",
            }

        service_labels = label_matrix[service]
        service_df = service_features[service]

        if len(service_labels) != len(features_df):
            return {
                "status": "error",
                "message": (
                    f"Label count mismatch for {service}: "
                    f"{len(service_labels)} labels for "
                    f"{len(features_df)} windows"
                ),
            }

        if not service_df.index.equals(features_df.index):
            return {
                "status": "error",
                "message": (
                    f"Feature timestamps do not match for {service}"
                ),
            }

        try:
            X_service = _build_service_matrix(
                features_df,
                service_df,
                service_ids[service],
            )
        except ValueError as exc:
            return {
                "status": "error",
                "message": str(exc),
            }

        for i, label in enumerate(service_labels):
            if label not in (0, 1, False, True):
                return {
                    "status": "error",
                    "message:": (
                        f"Invalid binary label for service: {service}"
                    ),
                }

            rows.append(X_service[i])
            labels.append(int(label))

    if not rows:
        return {
            "status": "insufficient_data",
            "message": "No labeled samples available",
        }

    X_all = np.asarray(rows, dtype=float)
    y_all = np.asarray(labels, dtype=int)

    if len(np.unique(y_all)) < 2:
        return {
            "status": "insufficient_labels",
            "message": (
                "Training requires both positive and negative labels. "
                "Provide logs containing examples of both outcomes."
            ),
        }

    auc = None

    # Attempt a stratified holdout evaluation.
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X_all,
            y_all,
            test_size=0.25,
            random_state=42,
            stratify=y_all,
        )

        if (
            len(np.unique(y_train)) == 2
            and len(np.unique(y_test)) == 2
        ):
            evaluation_model = xgb.train(
                _model_params(),
                xgb.DMatrix(X_train, label=y_train),
                num_boost_round=NUM_BOOST_ROUNDS,
            )

            probabilities = evaluation_model.predict(
                xgb.DMatrix(X_test)
            )

            auc = float(
                roc_auc_score(y_test, probabilities)
            )

    except ValueError:
        # AUC may be unavailable for very small datasets.
        auc = None

    # Train the final model on every labeled sample.
    model = xgb.train(
        _model_params(),
        xgb.DMatrix(X_all, label=y_all),
        num_boost_round=NUM_BOOST_ROUNDS,
    )

    model.set_attr(
        model_version=MODEL_VERSION,
        service_mapping=json.dumps(
            service_ids,
            sort_keys=True,
        ),
        feature_columns=json.dumps(ALL_FEATURE_COLS),
        input_width=str(X_all.shape[1]),
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(MODEL_PATH))

    return {
        "status": "trained",
        "auc": round(auc, 4) if auc is not None else None,
        "n_samples": int(len(X_all)),
        "n_windows": int(len(features_df)),
        "n_services": len(service_ids),
        "positive_rate": round(float(y_all.mean()), 3),
        "model_path": str(MODEL_PATH),
        "feature_cols": ALL_FEATURE_COLS,
        "input_width": int(X_all.shape[1]),
        "auc_note": (
            None
            if auc is not None
            else (
                "AUC unavailable: too few samples for a valid "
                "stratified holdout"
            )
        ),
    }


def predict_failure_risk(
    features_df: pd.DataFrame,
    services: list[str],
    service_features: dict[str, pd.DataFrame],
    latest_window_only: bool = True,
    horizon_minutes: int = 3,
) -> dict:
    """Predict failure risk per service for the latest feature window."""
    if not MODEL_PATH.exists():
        return {
            "error": (
                "Model not trained yet. "
                "Call /api/predict/train/seed first."
            )
        }

    model = xgb.Booster()
    model.load_model(str(MODEL_PATH))

    saved_version = model.attr("model_version")

    if saved_version != MODEL_VERSION:
        return {
            "error": (
                "The saved model uses an older or incompatible format. "
                "Retrain it using /api/predict/train/seed."
            )
        }

    saved_columns = model.attr("feature_columns")
    expected_columns = json.dumps(ALL_FEATURE_COLS)

    if saved_columns != expected_columns:
        return {
            "error": (
                "The model feature configuration does not match this "
                "code. Retrain the model."
            )
        }

    saved_width = model.attr("input_width")

    if saved_width != str(len(ALL_FEATURE_COLS) + 1):
        return {
            "error": (
                "The saved model input width is incompatible. "
                "Retrain the model."
            )
        }

    saved_mapping = model.attr("service_mapping")

    if not saved_mapping:
        return {
            "error": (
                "The model has no saved service mapping. Retrain it."
            )
        }

    service_ids = json.loads(saved_mapping)

    if features_df.empty:
        return {
            "error": "No feature windows available for prediction"
        }

    missing = _validate_global_features(features_df)

    if missing:
        return {
            "error": f"Missing feature columns: {missing}"
        }

    if latest_window_only:
        features_df = features_df.iloc[[-1]].copy()

    predictions = []

    for service in sorted(set(services)):
        if service not in service_features:
            return {
                "error": (
                    f"Missing service-specific features for {service}"
                )
            }

        service_df = service_features[service]

        # Select the exact feature timestamps being predicted.
        service_df = service_df.reindex(features_df.index)

        if service_df[SERVICE_FEATURE_COLS].isna().any().any():
            return {
                "error": (
                    f"Missing or misaligned service features for {service}"
                )
            }

        # Unknown services were not learned during training.
        # Do not silently assign an arbitrary ID to them.
        if service not in service_ids:
            predictions.append({
                "service": service,
                "risk": None,
                "risk_percent": None,
                "risk_level": "unknown",
                "message": "Service was not present during training",
            })
            continue

        try:
            X_service = _build_service_matrix(
                features_df,
                service_df,
                service_ids[service],
            )
        except ValueError as exc:
            return {"error": str(exc)}

        probabilities = model.predict(
            xgb.DMatrix(X_service)
        )

        risk = float(probabilities[-1])

        predictions.append({
            "service": service,
            "risk": round(risk, 4),
            "risk_percent": round(risk * 100, 1),
            "risk_level": _risk_to_level(risk),
        })

    # Known risk scores first, highest risk first.
    predictions.sort(
        key=lambda item: (
            item["risk"] is not None,
            item["risk"] if item["risk"] is not None else -1,
        ),
        reverse=True,
    )

    return {
        "predictions": predictions,
        "window_start": features_df.index[-1].isoformat(),
        "horizon_minutes": horizon_minutes,
        "model_loaded": True,
        "model_version": MODEL_VERSION,
    }


def _risk_to_level(risk: float) -> str:
    if risk >= 0.7:
        return "critical"
    elif risk >= 0.5:
        return "high"
    elif risk >= 0.3:
        return "medium"

    return "low"
