
import math

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "total_logs",
    "error_count",
    "warn_count",
    "error_rate",
    "unique_templates",
    "unique_services",
    "max_template_freq",
    "template_entropy",
]

REQUIRED_COLUMNS = ["timestamp", "level", "service", "cluster_id"]


def parsed_lines_to_dataframe(parsed_lines: list[dict]) -> pd.DataFrame:
    """
    Convert parsed logs into a validated DataFrame.

    Invalid timestamps are discarded. Missing service/template values
    receive stable fallback values so they don't break aggregation.
    """
    if not parsed_lines:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.DataFrame(parsed_lines)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"Parsed logs are missing required fields: {', '.join(missing)}"
        )

    df = df.copy()

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="coerce", utc=True
    )

    df = df.dropna(subset=["timestamp"])

    if df.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    # Use consistent, case-insensitive log levels.
    df["level"] = (
        df["level"]
        .fillna("UNKNOWN")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["service"] = (
        df["service"]
        .fillna("unknown")
        .astype(str)
        .str.strip()
        .replace("", "unknown")
    )

    df["cluster_id"] = (
        df["cluster_id"]
        .fillna("unknown")
        .astype(str)
        .str.strip()
        .replace("", "unknown")
    )

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def build_window_features(
    df: pd.DataFrame,
    window_minutes: int = 1,
) -> pd.DataFrame:
    """
    Build fixed-size, minute-aligned log feature windows.

    Empty windows between the first and last timestamps are retained.
    Windows outside the observed time range are not fabricated.
    """
    if not isinstance(window_minutes, int) or isinstance(window_minutes, bool):
        raise ValueError("window_minutes must be an integer")

    if not 1 <= window_minutes <= 1440:
        raise ValueError("window_minutes must be between 1 and 1440")

    if df.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"DataFrame is missing required fields: {', '.join(missing)}"
        )

    work = df.copy()

    work["timestamp"] = pd.to_datetime(
        work["timestamp"], errors="coerce", utc=True
    )
    work = work.dropna(subset=["timestamp"])

    if work.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    work["level"] = (
        work["level"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
    )
    work["service"] = (
        work["service"].fillna("unknown").astype(str).replace("", "unknown")
    )
    work["cluster_id"] = (
        work["cluster_id"].fillna("unknown").astype(str).replace("", "unknown")
    )

    work = work.set_index("timestamp").sort_index()

    # UTC and a fixed origin make window assignment consistent.
    grouped = work.resample(
        f"{window_minutes}min",
        origin="epoch",
        closed="left",
        label="left",
    )

    rows = []

    for window_start, window_df in grouped:
        total = len(window_df)

        if total == 0:
            rows.append({
                "window_start": window_start,
                "total_logs": 0,
                "error_count": 0,
                "warn_count": 0,
                "error_rate": 0.0,
                "unique_templates": 0,
                "unique_services": 0,
                "max_template_freq": 0,
                "template_entropy": 0.0,
            })
            continue

        error_count = int((window_df["level"] == "ERROR").sum())
        warn_count = int((window_df["level"] == "WARN").sum())

        template_counts = window_df["cluster_id"].value_counts()
        probabilities = template_counts.to_numpy(dtype=float) / total

        entropy = (
            -float(np.sum(probabilities * np.log2(probabilities)))
            if len(probabilities) > 1
            else 0.0
        )

        rows.append({
            "window_start": window_start,
            "total_logs": total,
            "error_count": error_count,
            "warn_count": warn_count,
            "error_rate": error_count / total,
            "unique_templates": int(len(template_counts)),
            "unique_services": int(window_df["service"].nunique()),
            "max_template_freq": int(template_counts.max()),
            "template_entropy": entropy,
        })

    if not rows:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    features_df = (
        pd.DataFrame(rows)
        .set_index("window_start")
        .sort_index()
    )

    return features_df[FEATURE_COLUMNS].replace(
        [np.inf, -np.inf], np.nan
    ).fillna(0)


def select_model_features(features_df: pd.DataFrame) -> pd.DataFrame:
    """Return clean, numeric features in a consistent column order."""
    if features_df.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS, index=features_df.index)

    missing = [
        column for column in FEATURE_COLUMNS
        if column not in features_df.columns
    ]
    if missing:
        raise ValueError(
            f"Missing model features: {', '.join(missing)}"
        )

    result = features_df[FEATURE_COLUMNS].copy()

    for column in FEATURE_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result = result.replace([np.inf, -np.inf], np.nan).fillna(0)

    if not np.isfinite(result.to_numpy(dtype=float)).all():
        raise ValueError("Model features contain non-finite values")

    return result
