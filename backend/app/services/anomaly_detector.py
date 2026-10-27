
import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from backend.app.services.feature_engineer import (
    parsed_lines_to_dataframe,
    build_window_features,
    select_model_features,
)

logger = logging.getLogger(__name__)

MIN_MODEL_WINDOWS = 3

# Initial thresholds; tune against real production traffic.
MIN_ERRORS_FOR_RULE = 3
MIN_ERROR_RATE_FOR_RULE = 0.30


def detect_anomalies(
    parsed_lines: list[dict],
    window_minutes: int = 1,
    contamination: float = 0.15,
) -> dict:
    """
    Detect log anomalies using Isolation Forest and error-burst rules.

    Isolation Forest is used when at least three windows are available.
    Rule-based detection also works with a single window.

    The response preserves the existing windows, anomaly_windows, and
    summary fields. An error field is included for empty input.
    """
    if (
        not isinstance(window_minutes, int)
        or isinstance(window_minutes, bool)
        or not 1 <= window_minutes <= 1440
    ):
        raise ValueError("window_minutes must be an integer from 1 to 1440")

    if (
        not isinstance(contamination, (int, float))
        or isinstance(contamination, bool)
        or not np.isfinite(contamination)
        or not 0 < contamination < 0.5
    ):
        raise ValueError("contamination must be between 0 and 0.5")

    empty_result = {
        "windows": [],
        "anomaly_windows": [],
        "summary": {
            "total_windows": 0,
            "anomaly_windows": 0,
            "anomaly_rate": 0.0,
            "window_minutes": window_minutes,
            "contamination": float(contamination),
            "detector": "none",
            "model_used": False,
            "rule_based_windows": 0,
            "services_in_anomalies": [],
        },
    }

    if not parsed_lines:
        return {
            **empty_result,
            "error": "No valid log lines provided",
        }

    try:
        df = parsed_lines_to_dataframe(parsed_lines)

        if df.empty:
            return {
                **empty_result,
                "error": "No valid log lines provided",
            }

        features_df = build_window_features(
            df,
            window_minutes=window_minutes,
        )

        if features_df.empty:
            return {
                **empty_result,
                "error": "No valid time windows could be created",
            }

        X = select_model_features(features_df)
        numeric_X = X.to_numpy(dtype=float)

        if not np.isfinite(numeric_X).all():
            raise ValueError("Model features contain non-finite values")

    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Could not prepare anomaly detection data: %s", exc)
        raise

    n_windows = len(X)

    # Rule-based detection is independent of the ML model.
    error_counts = features_df["error_count"].to_numpy(dtype=int)
    error_rates = features_df["error_rate"].to_numpy(dtype=float)

    rule_flags = (
        (error_counts >= MIN_ERRORS_FOR_RULE)
        & (error_rates >= MIN_ERROR_RATE_FOR_RULE)
    )

    labels = np.ones(n_windows, dtype=int)
    scores = np.zeros(n_windows, dtype=float)
    model_used = False

    if n_windows >= MIN_MODEL_WINDOWS:
        try:
            model = IsolationForest(
                n_estimators=300,
                contamination=float(contamination),
                max_samples="auto",
                random_state=42,
                n_jobs=-1,
            )

            model.fit(numeric_X)
            labels = model.predict(numeric_X)
            scores = model.decision_function(numeric_X)
            model_used = True

        except (ValueError, FloatingPointError):
            logger.exception(
                "Isolation Forest failed; using rule-based detection"
            )

            labels = np.ones(n_windows, dtype=int)
            scores = np.zeros(n_windows, dtype=float)
            model_used = False

    # Isolation Forest: -1 means anomalous.
    # Rules independently flag high-error windows.
    anomaly_flags = (labels == -1) | rule_flags

    windows = []

    for index, (timestamp, row) in enumerate(features_df.iterrows()):
        score = float(scores[index])
        error_count = int(row["error_count"])
        error_rate = float(row["error_rate"])
        is_anomaly = bool(anomaly_flags[index])
        rule_based = bool(rule_flags[index])

        if rule_based and error_count >= 5 and error_rate >= 0.75:
            severity = "critical"
        elif rule_based:
            severity = "high"
        elif is_anomaly:
            severity = _score_to_severity(score)
            # A model anomaly must not be presented as normal merely
            # because its decision score is positive.
            if severity == "normal":
                severity = "medium"
        else:
            severity = "normal"

        windows.append({
            "window_start": timestamp.isoformat(),
            "total_logs": int(row["total_logs"]),
            "error_count": error_count,
            "warn_count": int(row["warn_count"]),
            "error_rate": round(error_rate, 4),
            "unique_templates": int(row["unique_templates"]),
            "unique_services": int(row["unique_services"]),
            "max_template_freq": int(row["max_template_freq"]),
            "template_entropy": round(
                float(row["template_entropy"]), 4
            ),
            "is_anomaly": is_anomaly,
            "anomaly_score": round(score, 4),
            "severity": severity,
        })

    anomaly_windows = [
        window for window in windows if window["is_anomaly"]
    ]

    anomaly_count = len(anomaly_windows)

    # Include actual services from anomalous time windows.
    work = df.copy()
    work["timestamp"] = pd.to_datetime(
        work["timestamp"], errors="coerce", utc=True
    )
    work = work.dropna(subset=["timestamp"])

    anomalous_services = set()

    for window in anomaly_windows:
        start = pd.Timestamp(window["window_start"])
        end = start + pd.Timedelta(minutes=window_minutes)

        matching = work.loc[
            (work["timestamp"] >= start)
            & (work["timestamp"] < end)
        ]

        if "service" in matching.columns:
            anomalous_services.update(
                matching["service"].dropna().astype(str).tolist()
            )

    summary = {
        "total_windows": n_windows,
        "anomaly_windows": anomaly_count,
        "anomaly_rate": round(anomaly_count / n_windows, 3),
        "window_minutes": window_minutes,
        "contamination": float(contamination),
        "detector": (
            "isolation_forest+rules"
            if model_used
            else "rules_only"
        ),
        "model_used": model_used,
        "rule_based_windows": int(rule_flags.sum()),
        "services_in_anomalies": sorted(anomalous_services)[:5],
    }

    if not model_used:
        summary["message"] = (
            "Rule-based detection was used because fewer than "
            f"{MIN_MODEL_WINDOWS} windows were available or the "
            "model could not be fitted."
        )

    return {
        "windows": windows,
        "anomaly_windows": anomaly_windows,
        "summary": summary,
    }


def _score_to_severity(score: float) -> str:
    """
    Map an Isolation Forest decision score to a severity label.

    Lower scores indicate more anomalous observations.
    This mapping preserves the existing one-argument API.
    """
    if score < -0.15:
        return "critical"
    elif score < -0.05:
        return "high"
    elif score < 0.0:
        return "medium"
    else:
        return "normal"
