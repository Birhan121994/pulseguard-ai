
import pandas as pd

from backend.app.services.log_parser import parse_log_text
from backend.app.services.anomaly_detector import detect_anomalies
from backend.app.services.feature_engineer import (
    parsed_lines_to_dataframe,
    build_window_features,
)
from backend.app.services.failure_labeler import (
    build_service_level_labels,
    build_service_features,
)
from backend.app.services.failure_predictor import (
    train_failure_model,
    predict_failure_risk,
)


# Keep these values consistent with the feature builder and labeler.
WINDOW_MINUTES = 1 / 6
WINDOW_SECONDS = 10
HORIZON_MINUTES = 3


def _extract_features(raw_text: str):
    """Parse logs and build consistent global feature windows."""
    parsed = parse_log_text(raw_text)

    if parsed["parsed_lines"] == 0:
        return None, {"error": "No lines parsed"}

    df = parsed_lines_to_dataframe(parsed["lines"])

    if df.empty:
        return None, {"error": "No valid log records found"}

    if "timestamp" not in df.columns:
        return None, {"error": "Log records are missing timestamps"}

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        utc=True,
    )

    df = df.dropna(subset=["timestamp"]).copy()

    if df.empty:
        return None, {"error": "No valid timestamps found"}

    features_df = build_window_features(
        df,
        window_minutes=WINDOW_MINUTES,
    )

    if features_df.empty:
        return None, {"error": "No feature windows generated"}

    return (parsed, features_df), None


def _build_training_data(parsed, features_df):
    """Build labels and service features using identical timestamps."""
    label_data = build_service_level_labels(
        parsed["lines"],
        features_df,
        horizon_minutes=HORIZON_MINUTES,
        window_seconds=WINDOW_SECONDS,
    )

    # Always use the normalized, sorted feature index returned by
    # the labeler for both service features and model training.
    aligned_features = label_data["features"]

    service_features = build_service_features(
        parsed["lines"],
        aligned_features,
        label_data["services"],
        window_seconds=WINDOW_SECONDS,
    )

    return label_data, aligned_features, service_features


def run_training_pipeline(raw_text: str) -> dict:
    """Parse logs, generate service labels/features, and train."""
    extracted, error = _extract_features(raw_text)

    if error:
        return error

    parsed, features_df = extracted

    if len(features_df) < 2:
        return {
            "error": (
                f"Need at least 2 feature windows; "
                f"generated {len(features_df)}. "
                "Provide logs spanning at least two windows."
            )
        }

    # Preserve the existing anomaly-detection pipeline.
    # Service-level failure labels are generated separately below.
    detect_anomalies(
        parsed["lines"],
        window_minutes=1,
        contamination=0.15,
    )

    label_data, aligned_features, service_features = (
        _build_training_data(parsed, features_df)
    )

    if not label_data["services"]:
        return {
            "status": "insufficient_data",
            "message": "No services found in the training logs",
        }

    # print("Services:", label_data["services"])
    # print("Training windows:", len(aligned_features))

    for service, labels in label_data["label_matrix"].items():
        # print(
        #     f"{service}: labels={labels}, "
        #     f"positive={sum(labels)}, "
        #     f"negative={len(labels) - sum(labels)}"
        # )

        service_df = service_features[service]

        print(
            f"{service}: total service errors="
            f"{int(service_df['service_error_count'].sum())}, "
            f"total service warnings="
            f"{int(service_df['service_warn_count'].sum())}"
        )

    result = train_failure_model(
        aligned_features,
        label_data["label_matrix"],
        label_data["services"],
        service_features,
    )

    result["services"] = label_data["services"]
    result["n_windows"] = len(aligned_features)

    return result


def run_prediction_pipeline(raw_text: str) -> dict:
    """Parse logs, build matching features, and predict service risk."""
    extracted, error = _extract_features(raw_text)

    if error:
        return error

    parsed, features_df = extracted

    label_data, aligned_features, service_features = (
        _build_training_data(parsed, features_df)
    )

    return predict_failure_risk(
        features_df=aligned_features,
        services=label_data["services"],
        service_features=service_features,
        latest_window_only=True,
        horizon_minutes=HORIZON_MINUTES,
    )
