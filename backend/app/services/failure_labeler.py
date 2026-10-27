
import pandas as pd


DEFAULT_WINDOW_SECONDS = 10


def _to_utc_timestamp(value) -> pd.Timestamp:
    """Convert a timestamp to timezone-aware UTC."""
    timestamp = pd.Timestamp(value)

    if pd.isna(timestamp):
        raise ValueError(
            "Invalid timestamp encountered in failure labeler"
        )

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def _normalize_log_dataframe(
    parsed_lines: list[dict],
) -> pd.DataFrame:
    """Normalize log timestamps and fields before labeling."""
    df = pd.DataFrame(parsed_lines)

    if df.empty:
        return df

    required = {"timestamp", "service", "level"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Parsed logs are missing required fields: {sorted(missing)}"
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        utc=True,
    )

    df = df.dropna(subset=["timestamp"]).copy()

    df["service"] = (
        df["service"]
        .fillna("unknown")
        .astype(str)
        .str.strip()
    )
    df.loc[df["service"] == "", "service"] = "unknown"

    df["level"] = (
        df["level"]
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df.sort_values("timestamp").reset_index(drop=True)


def _normalize_feature_index(
    features_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return features with a sorted UTC DatetimeIndex."""
    result = features_df.copy()

    result.index = pd.DatetimeIndex(
        [_to_utc_timestamp(value) for value in result.index]
    )

    return result.sort_index()


def generate_failure_labels(
    features_df: pd.DataFrame,
    anomaly_windows: list[dict],
    horizon_minutes: int = 3,
) -> pd.DataFrame:
    """
    Label a feature window positive if an anomaly window starts
    strictly after the current start and within the future horizon.
    """
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be greater than zero")

    if features_df.empty:
        return pd.DataFrame()

    result = _normalize_feature_index(features_df)

    anomaly_times = set()

    for anomaly in anomaly_windows:
        if anomaly.get("error_count", 0) > 0:
            anomaly_times.add(
                _to_utc_timestamp(anomaly["window_start"])
            )

    horizon = pd.Timedelta(minutes=horizon_minutes)
    labels = []

    for window_start in result.index:
        window_end = window_start + horizon

        future_anomaly = any(
            window_start < anomaly_time <= window_end
            for anomaly_time in anomaly_times
        )

        labels.append(int(future_anomaly))

    result["will_fail_next"] = labels

    return result


def build_service_level_labels(
    parsed_lines: list[dict],
    features_df: pd.DataFrame,
    horizon_minutes: int = 3,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> dict:
    """
    Build future-error labels for each service and feature window.

    A label is 1 if an ERROR from that service occurs at or after
    the current window's end, but strictly before the end of the
    configured prediction horizon.

    Feature windows use half-open intervals:
        [window_start, window_start + window_seconds)
    """
    if horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be greater than zero")

    if window_seconds <= 0:
        raise ValueError("window_seconds must be greater than zero")

    result_features = _normalize_feature_index(features_df)

    empty_result = {
        "services": [],
        "label_matrix": {},
        "features": result_features,
    }

    if result_features.empty or not parsed_lines:
        return empty_result

    df = _normalize_log_dataframe(parsed_lines)

    if df.empty:
        return empty_result

    services = sorted(df["service"].unique().tolist())

    error_times_by_service = {
        service: []
        for service in services
    }

    error_rows = df.loc[df["level"] == "ERROR"]

    for row in error_rows.itertuples(index=False):
        error_times_by_service[row.service].append(row.timestamp)

    window_delta = pd.Timedelta(seconds=window_seconds)
    horizon_delta = pd.Timedelta(minutes=horizon_minutes)

    label_matrix = {}

    for service in services:
        error_times = error_times_by_service[service]
        labels = []

        for window_start in result_features.index:
            current_window_end = window_start + window_delta
            horizon_end = window_start + horizon_delta

            future_error = any(
                current_window_end <= error_time < horizon_end
                for error_time in error_times
            )

            labels.append(int(future_error))

        label_matrix[service] = labels

    return {
        "services": services,
        "label_matrix": label_matrix,
        "features": result_features,
    }


def build_service_features(
    parsed_lines: list[dict],
    features_df: pd.DataFrame,
    services: list[str],
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> dict[str, pd.DataFrame]:
    """
    Build per-service log counts aligned to the feature windows.

    These features allow the model to distinguish a service with
    many errors from another service in the same global window.
    """
    if window_seconds <= 0:
        raise ValueError("window_seconds must be greater than zero")

    result_features = _normalize_feature_index(features_df)

    df = _normalize_log_dataframe(parsed_lines)

    if df.empty:
        return {
            service: pd.DataFrame(
                0,
                index=result_features.index,
                columns=[
                    "service_log_count",
                    "service_error_count",
                    "service_warn_count",
                ],
                dtype=int,
            )
            for service in services
        }

    window_delta = pd.Timedelta(seconds=window_seconds)
    result = {}

    for service in sorted(set(services)):
        service_logs = df.loc[df["service"] == service]
        rows = []

        # Use exactly the same window boundaries as feature engineering.
        for window_start in result_features.index:
            window_end = window_start + window_delta

            window_logs = service_logs.loc[
                (service_logs["timestamp"] >= window_start)
                & (service_logs["timestamp"] < window_end)
            ]

            rows.append({
                "service_log_count": int(len(window_logs)),
                "service_error_count": int(
                    (window_logs["level"] == "ERROR").sum()
                ),
                "service_warn_count": int(
                    (window_logs["level"] == "WARN").sum()
                ),
            })

        result[service] = pd.DataFrame(
            rows,
            index=result_features.index,
            columns=[
                "service_log_count",
                "service_error_count",
                "service_warn_count",
            ],
        )

    return result
