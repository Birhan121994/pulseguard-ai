import logging
import os
import re
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd
from google import genai
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# Initialize Gemini client lazily (module-level import is fine, but client
# creation is deferred until first use to avoid startup failures if the
# API key is missing in some test environments).
_GEMINI_CLIENT = None

FAILURE_PATTERN = re.compile(
    r"\b("
    r"fail(?:ed|ure|ures)?|"
    r"exception|"
    r"timeout|timed out|"
    r"error|"
    r"unavailable|"
    r"refused|"
    r"crash(?:ed)?|"
    r"deadlock|"
    r"rejected|"
    r"5\d\d"
    r")\b",
    re.IGNORECASE,
)

SERVICE_PATTERN = re.compile(
    r"\bservice\s*=\s*([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)


def get_gemini_client() -> genai.Client:
    """Lazily create and reuse the Gemini API client."""
    global _GEMINI_CLIENT

    if _GEMINI_CLIENT is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
        _GEMINI_CLIENT = genai.Client(api_key=api_key)

    return _GEMINI_CLIENT


def _get_embeddings(texts: list[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts using Gemini's text-embedding-004.

    Returns a 2D numpy array with one row per input text and 768 columns.
    Raises RuntimeError if the API call fails or returns an unexpected shape.
    """
    client = get_gemini_client()

    # Gemini's embed_content accepts a list of contents for batch embedding
    result = client.models.embed_content(
        model="text-embedding-004",
        contents=texts,
        config={
            "task_type": "CLUSTERING",  # optimal for DBSCAN clustering
        },
    )

    if not result.embeddings or len(result.embeddings) != len(texts):
        raise RuntimeError(
            f"Gemini returned {len(result.embeddings or [])} embeddings "
            f"for {len(texts)} input texts"
        )

    embeddings = np.array([emb.values for emb in result.embeddings], dtype=np.float32)

    # Gemini embeddings are already normalized, but we normalize again
    # to be safe (DBSCAN with cosine metric benefits from unit vectors).
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    return embeddings


def _parse_timestamp(value) -> pd.Timestamp | None:
    """Parse a timestamp consistently; interpret naive timestamps as UTC."""
    if value is None:
        return None

    try:
        timestamp = pd.Timestamp(value)

        if pd.isna(timestamp):
            return None

        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")

        return timestamp

    except (TypeError, ValueError, OverflowError):
        return None


def _is_failure_line(line: dict) -> bool:
    """
    Select failure-related logs, excluding normal successful traffic.

    ERROR logs are retained. WARN logs are retained when they contain
    a recognizable failure signal.
    """
    level = str(line.get("level", "UNKNOWN")).strip().upper()
    message = str(line.get("message", ""))

    if level in {"ERROR", "FATAL", "CRITICAL"}:
        return True

    return bool(FAILURE_PATTERN.search(message))


def _line_services(line: dict) -> set[str]:
    """
    Include the emitting service and downstream services named in a
    message, such as service=payment-service.
    """
    services = set()

    service = line.get("service")
    if service:
        services.add(str(service).strip())

    message = str(line.get("message", ""))

    for match in SERVICE_PATTERN.finditer(message):
        services.add(match.group(1).strip())

    services.discard("")
    return services


def _infer_incident_severity(
    line_count: int,
    levels: list[str],
    messages: list[str] | None = None,
) -> str:
    """Infer severity from error volume, error ratio, and failure patterns."""
    if line_count <= 0:
        return "low"

    normalized_levels = [
        str(level).strip().upper() for level in levels
    ]

    error_count = sum(
        level in {"ERROR", "FATAL", "CRITICAL"}
        for level in normalized_levels
    )

    error_ratio = error_count / line_count

    combined_messages = " ".join(messages or [])
    has_payment_failure = bool(
        re.search(
            r"payment.{0,40}(fail|timeout|error)|"
            r"(fail|timeout|error).{0,40}payment",
            combined_messages,
            re.IGNORECASE,
        )
    )

    # Repeated payment failures are a strong signal, but this is a
    # heuristic and should be calibrated against production incidents.
    if error_count >= 5 and error_ratio >= 0.70:
        return "critical"

    if error_count >= 3 and error_ratio >= 0.50:
        return "high"

    if has_payment_failure and error_count >= 3:
        return "high"

    if error_count >= 2:
        return "medium"

    if error_count >= 1 or line_count >= 3:
        return "medium"

    return "low"


def cluster_anomalous_lines(
    anomaly_windows: list[dict],
    parsed_lines: list[dict],
    eps: float = 0.35,
    min_samples: int = 2,
    window_minutes: int = 1,
) -> dict:
    """
    Extract failure-related logs from anomalous windows and group them
    into incidents using semantic embeddings and DBSCAN.

    Args:
        anomaly_windows: Output from detect_anomalies()["anomaly_windows"].
        parsed_lines: Parsed log records.
        eps: DBSCAN cosine-distance threshold.
        min_samples: Minimum records required to form a cluster.
        window_minutes: Duration of each anomaly window.

    Returns:
        Incident clusters, noise information, and a summary.
    """
    if not isinstance(window_minutes, int) or isinstance(window_minutes, bool):
        raise ValueError("window_minutes must be an integer")

    if not 1 <= window_minutes <= 1440:
        raise ValueError("window_minutes must be between 1 and 1440")

    if not np.isfinite(eps) or not 0 < eps <= 2:
        raise ValueError("eps must be between 0 and 2")

    if not isinstance(min_samples, int) or isinstance(min_samples, bool):
        raise ValueError("min_samples must be an integer")

    if min_samples < 1:
        raise ValueError("min_samples must be at least 1")

    if not anomaly_windows:
        return {
            "incidents": [],
            "noise_count": 0,
            "noise_samples": [],
            "total_anomalous_lines": 0,
            "total_clusters": 0,
            "summary": {
                "message": "No anomaly windows provided",
                "clusters_found": 0,
                "noise_lines": 0,
                "largest_cluster_size": 0,
                "eps": eps,
                "min_samples": min_samples,
            },
        }

    # Convert windows to half-open UTC intervals: [start, end).
    intervals = []

    for window in anomaly_windows:
        start = _parse_timestamp(window.get("window_start"))

        if start is None:
            logger.warning(
                "Skipping anomaly window with invalid timestamp: %r",
                window.get("window_start"),
            )
            continue

        intervals.append(
            (start, start + pd.Timedelta(minutes=window_minutes))
        )

    if not intervals:
        return {
            "incidents": [],
            "noise_count": 0,
            "noise_samples": [],
            "total_anomalous_lines": 0,
            "total_clusters": 0,
            "summary": {
                "message": "No valid anomaly window timestamps",
                "clusters_found": 0,
                "noise_lines": 0,
                "largest_cluster_size": 0,
                "eps": eps,
                "min_samples": min_samples,
            },
        }

    # Restrict clustering to the flagged time intervals.
    anomalous_lines = []
    seen = set()

    for line in parsed_lines:
        timestamp = _parse_timestamp(line.get("timestamp"))

        if timestamp is None:
            continue

        inside_window = any(
            start <= timestamp < end
            for start, end in intervals
        )

        if not inside_window or not _is_failure_line(line):
            continue

        # Avoid duplicate records if the input contains repeated objects.
        identity = (
            timestamp.isoformat(),
            str(line.get("service", "")),
            str(line.get("level", "")),
            str(line.get("message", "")),
        )

        if identity in seen:
            continue

        seen.add(identity)

        normalized_line = dict(line)
        normalized_line["_parsed_timestamp"] = timestamp
        anomalous_lines.append(normalized_line)

    anomalous_lines.sort(key=lambda line: line["_parsed_timestamp"])

    if not anomalous_lines:
        return {
            "incidents": [],
            "noise_count": 0,
            "noise_samples": [],
            "total_anomalous_lines": 0,
            "total_clusters": 0,
            "summary": {
                "message": (
                    "Anomaly windows contained no matching failure-related "
                    "log lines."
                ),
                "clusters_found": 0,
                "noise_lines": 0,
                "largest_cluster_size": 0,
                "eps": eps,
                "min_samples": min_samples,
            },
        }

    # If there are fewer records than min_samples, DBSCAN cannot form
    # a cluster. Return them as noise rather than calling the embedding API.
    if len(anomalous_lines) < min_samples:
        samples = [
            str(line.get("message", "")) for line in anomalous_lines[:5]
        ]

        return {
            "incidents": [],
            "noise_count": len(anomalous_lines),
            "noise_samples": samples,
            "total_anomalous_lines": len(anomalous_lines),
            "total_clusters": 0,
            "summary": {
                "message": (
                    f"Only {len(anomalous_lines)} failure-related lines; "
                    f"DBSCAN needs at least {min_samples}."
                ),
                "clusters_found": 0,
                "noise_lines": len(anomalous_lines),
                "largest_cluster_size": 0,
                "eps": eps,
                "min_samples": min_samples,
            },
        }

    messages = [
        str(line.get("message") or line.get("template") or "Unknown log")
        for line in anomalous_lines
    ]

    # --- Gemini Embedding API call (replaces local sentence-transformers) ---
    try:
        embeddings = _get_embeddings(messages)
    except Exception as exc:
        logger.error("Gemini embedding failed: %s", exc)
        # Return a graceful error instead of crashing the entire request
        return {
            "incidents": [],
            "noise_count": 0,
            "noise_samples": [],
            "total_anomalous_lines": len(anomalous_lines),
            "total_clusters": 0,
            "summary": {
                "message": f"Embedding API failed: {type(exc).__name__}",
                "clusters_found": 0,
                "noise_lines": 0,
                "largest_cluster_size": 0,
                "eps": eps,
                "min_samples": min_samples,
                "error": str(exc),
            },
        }

    dbscan = DBSCAN(
        eps=float(eps),
        min_samples=min_samples,
        metric="cosine",
    )

    labels = dbscan.fit_predict(embeddings)

    clusters = defaultdict(list)
    noise_lines = []

    for index, label in enumerate(labels):
        if label == -1:
            noise_lines.append(anomalous_lines[index])
        else:
            clusters[int(label)].append(anomalous_lines[index])

    incidents = []

    for cluster_id, lines in clusters.items():
        services = set()
        levels = []
        templates = []
        cluster_messages = []
        timestamps = []

        for line in lines:
            services.update(_line_services(line))

            levels.append(
                str(line.get("level", "UNKNOWN")).strip().upper()
            )

            template = line.get("template")
            if template:
                templates.append(str(template))
            else:
                templates.append(
                    str(line.get("message", "Unknown log"))
                )

            cluster_messages.append(str(line.get("message", "")))
            timestamps.append(line["_parsed_timestamp"])

        unique_templates = list(dict.fromkeys(templates))
        error_count = sum(
            level in {"ERROR", "FATAL", "CRITICAL"}
            for level in levels
        )
        warn_count = sum(level == "WARN" for level in levels)

        incidents.append({
            "incident_id": int(cluster_id),
            "line_count": len(lines),
            "affected_services": sorted(services),
            "services_count": len(services),
            "error_count": error_count,
            "warn_count": warn_count,
            "time_range": {
                "start": min(timestamps).isoformat(),
                "end": max(timestamps).isoformat(),
            },
            "templates": unique_templates[:10],
            "sample_messages": cluster_messages[:3],
            "severity": _infer_incident_severity(
                len(lines),
                levels,
                cluster_messages,
            ),
        })

    incidents.sort(
        key=lambda incident: (
            incident["severity"] == "critical",
            incident["severity"] == "high",
            incident["error_count"],
            incident["line_count"],
        ),
        reverse=True,
    )

    # Reassign IDs in sorted order so the primary incident appears first.
    for incident_id, incident in enumerate(incidents):
        incident["incident_id"] = incident_id

    noise_samples = [
        str(line.get("message", "")) for line in noise_lines[:5]
    ]

    return {
        "incidents": incidents,
        "noise_count": len(noise_lines),
        "noise_samples": noise_samples,
        "total_anomalous_lines": len(anomalous_lines),
        "total_clusters": len(incidents),
        "summary": {
            "clusters_found": len(incidents),
            "noise_lines": len(noise_lines),
            "largest_cluster_size": max(
                (incident["line_count"] for incident in incidents),
                default=0,
            ),
            "eps": eps,
            "min_samples": min_samples,
            "window_minutes": window_minutes,
        },
    }










# import logging
# import re
# from collections import defaultdict
# from datetime import timedelta

# import numpy as np
# import pandas as pd
# from sentence_transformers import SentenceTransformer
# from sklearn.cluster import DBSCAN

# logger = logging.getLogger(__name__)

# _MODEL = None

# FAILURE_PATTERN = re.compile(
#     r"\b("
#     r"fail(?:ed|ure|ures)?|"
#     r"exception|"
#     r"timeout|timed out|"
#     r"error|"
#     r"unavailable|"
#     r"refused|"
#     r"crash(?:ed)?|"
#     r"deadlock|"
#     r"rejected|"
#     r"5\d\d"
#     r")\b",
#     re.IGNORECASE,
# )

# SERVICE_PATTERN = re.compile(
#     r"\bservice\s*=\s*([A-Za-z0-9_.-]+)",
#     re.IGNORECASE,
# )


# def get_embedding_model() -> SentenceTransformer:
#     """Load the embedding model lazily and reuse it."""
#     global _MODEL

#     if _MODEL is None:
#         _MODEL = SentenceTransformer("all-MiniLM-L6-v2")

#     return _MODEL


# def _parse_timestamp(value) -> pd.Timestamp | None:
#     """Parse a timestamp consistently; interpret naive timestamps as UTC."""
#     if value is None:
#         return None

#     try:
#         timestamp = pd.Timestamp(value)

#         if pd.isna(timestamp):
#             return None

#         if timestamp.tzinfo is None:
#             timestamp = timestamp.tz_localize("UTC")
#         else:
#             timestamp = timestamp.tz_convert("UTC")

#         return timestamp

#     except (TypeError, ValueError, OverflowError):
#         return None


# def _is_failure_line(line: dict) -> bool:
#     """
#     Select failure-related logs, excluding normal successful traffic.

#     ERROR logs are retained. WARN logs are retained when they contain
#     a recognizable failure signal.
#     """
#     level = str(line.get("level", "UNKNOWN")).strip().upper()
#     message = str(line.get("message", ""))

#     if level in {"ERROR", "FATAL", "CRITICAL"}:
#         return True

#     return bool(FAILURE_PATTERN.search(message))


# def _line_services(line: dict) -> set[str]:
#     """
#     Include the emitting service and downstream services named in a
#     message, such as service=payment-service.
#     """
#     services = set()

#     service = line.get("service")
#     if service:
#         services.add(str(service).strip())

#     message = str(line.get("message", ""))

#     for match in SERVICE_PATTERN.finditer(message):
#         services.add(match.group(1).strip())

#     services.discard("")
#     return services


# def _infer_incident_severity(
#     line_count: int,
#     levels: list[str],
#     messages: list[str] | None = None,
# ) -> str:
#     """Infer severity from error volume, error ratio, and failure patterns."""
#     if line_count <= 0:
#         return "low"

#     normalized_levels = [
#         str(level).strip().upper() for level in levels
#     ]

#     error_count = sum(
#         level in {"ERROR", "FATAL", "CRITICAL"}
#         for level in normalized_levels
#     )

#     error_ratio = error_count / line_count

#     combined_messages = " ".join(messages or [])
#     has_payment_failure = bool(
#         re.search(
#             r"payment.{0,40}(fail|timeout|error)|"
#             r"(fail|timeout|error).{0,40}payment",
#             combined_messages,
#             re.IGNORECASE,
#         )
#     )

#     # Repeated payment failures are a strong signal, but this is a
#     # heuristic and should be calibrated against production incidents.
#     if error_count >= 5 and error_ratio >= 0.70:
#         return "critical"

#     if error_count >= 3 and error_ratio >= 0.50:
#         return "high"

#     if has_payment_failure and error_count >= 3:
#         return "high"

#     if error_count >= 2:
#         return "medium"

#     if error_count >= 1 or line_count >= 3:
#         return "medium"

#     return "low"


# def cluster_anomalous_lines(
#     anomaly_windows: list[dict],
#     parsed_lines: list[dict],
#     eps: float = 0.35,
#     min_samples: int = 2,
#     window_minutes: int = 1,
# ) -> dict:
#     """
#     Extract failure-related logs from anomalous windows and group them
#     into incidents using semantic embeddings and DBSCAN.

#     Args:
#         anomaly_windows: Output from detect_anomalies()["anomaly_windows"].
#         parsed_lines: Parsed log records.
#         eps: DBSCAN cosine-distance threshold.
#         min_samples: Minimum records required to form a cluster.
#         window_minutes: Duration of each anomaly window.

#     Returns:
#         Incident clusters, noise information, and a summary.
#     """
#     if not isinstance(window_minutes, int) or isinstance(window_minutes, bool):
#         raise ValueError("window_minutes must be an integer")

#     if not 1 <= window_minutes <= 1440:
#         raise ValueError("window_minutes must be between 1 and 1440")

#     if not np.isfinite(eps) or not 0 < eps <= 2:
#         raise ValueError("eps must be between 0 and 2")

#     if not isinstance(min_samples, int) or isinstance(min_samples, bool):
#         raise ValueError("min_samples must be an integer")

#     if min_samples < 1:
#         raise ValueError("min_samples must be at least 1")

#     if not anomaly_windows:
#         return {
#             "incidents": [],
#             "noise_count": 0,
#             "noise_samples": [],
#             "total_anomalous_lines": 0,
#             "total_clusters": 0,
#             "summary": {
#                 "message": "No anomaly windows provided",
#                 "clusters_found": 0,
#                 "noise_lines": 0,
#                 "largest_cluster_size": 0,
#                 "eps": eps,
#                 "min_samples": min_samples,
#             },
#         }

#     # Convert windows to half-open UTC intervals: [start, end).
#     intervals = []

#     for window in anomaly_windows:
#         start = _parse_timestamp(window.get("window_start"))

#         if start is None:
#             logger.warning(
#                 "Skipping anomaly window with invalid timestamp: %r",
#                 window.get("window_start"),
#             )
#             continue

#         intervals.append(
#             (start, start + pd.Timedelta(minutes=window_minutes))
#         )

#     if not intervals:
#         return {
#             "incidents": [],
#             "noise_count": 0,
#             "noise_samples": [],
#             "total_anomalous_lines": 0,
#             "total_clusters": 0,
#             "summary": {
#                 "message": "No valid anomaly window timestamps",
#                 "clusters_found": 0,
#                 "noise_lines": 0,
#                 "largest_cluster_size": 0,
#                 "eps": eps,
#                 "min_samples": min_samples,
#             },
#         }

#     # Restrict clustering to the flagged time intervals.
#     anomalous_lines = []
#     seen = set()

#     for line in parsed_lines:
#         timestamp = _parse_timestamp(line.get("timestamp"))

#         if timestamp is None:
#             continue

#         inside_window = any(
#             start <= timestamp < end
#             for start, end in intervals
#         )

#         if not inside_window or not _is_failure_line(line):
#             continue

#         # Avoid duplicate records if the input contains repeated objects.
#         identity = (
#             timestamp.isoformat(),
#             str(line.get("service", "")),
#             str(line.get("level", "")),
#             str(line.get("message", "")),
#         )

#         if identity in seen:
#             continue

#         seen.add(identity)

#         normalized_line = dict(line)
#         normalized_line["_parsed_timestamp"] = timestamp
#         anomalous_lines.append(normalized_line)

#     anomalous_lines.sort(key=lambda line: line["_parsed_timestamp"])

#     if not anomalous_lines:
#         return {
#             "incidents": [],
#             "noise_count": 0,
#             "noise_samples": [],
#             "total_anomalous_lines": 0,
#             "total_clusters": 0,
#             "summary": {
#                 "message": (
#                     "Anomaly windows contained no matching failure-related "
#                     "log lines."
#                 ),
#                 "clusters_found": 0,
#                 "noise_lines": 0,
#                 "largest_cluster_size": 0,
#                 "eps": eps,
#                 "min_samples": min_samples,
#             },
#         }

#     # If there are fewer records than min_samples, DBSCAN cannot form
#     # a cluster. Return them as noise rather than loading the model.
#     if len(anomalous_lines) < min_samples:
#         samples = [
#             str(line.get("message", "")) for line in anomalous_lines[:5]
#         ]

#         return {
#             "incidents": [],
#             "noise_count": len(anomalous_lines),
#             "noise_samples": samples,
#             "total_anomalous_lines": len(anomalous_lines),
#             "total_clusters": 0,
#             "summary": {
#                 "message": (
#                     f"Only {len(anomalous_lines)} failure-related lines; "
#                     f"DBSCAN needs at least {min_samples}."
#                 ),
#                 "clusters_found": 0,
#                 "noise_lines": len(anomalous_lines),
#                 "largest_cluster_size": 0,
#                 "eps": eps,
#                 "min_samples": min_samples,
#             },
#         }

#     messages = [
#         str(line.get("message") or line.get("template") or "Unknown log")
#         for line in anomalous_lines
#     ]

#     model = get_embedding_model()
#     embeddings = model.encode(
#         messages,
#         show_progress_bar=False,
#         convert_to_numpy=True,
#         normalize_embeddings=True,
#     )

#     dbscan = DBSCAN(
#         eps=float(eps),
#         min_samples=min_samples,
#         metric="cosine",
#     )

#     labels = dbscan.fit_predict(embeddings)

#     clusters = defaultdict(list)
#     noise_lines = []

#     for index, label in enumerate(labels):
#         if label == -1:
#             noise_lines.append(anomalous_lines[index])
#         else:
#             clusters[int(label)].append(anomalous_lines[index])

#     incidents = []

#     for cluster_id, lines in clusters.items():
#         services = set()
#         levels = []
#         templates = []
#         cluster_messages = []
#         timestamps = []

#         for line in lines:
#             services.update(_line_services(line))

#             levels.append(
#                 str(line.get("level", "UNKNOWN")).strip().upper()
#             )

#             template = line.get("template")
#             if template:
#                 templates.append(str(template))
#             else:
#                 templates.append(
#                     str(line.get("message", "Unknown log"))
#                 )

#             cluster_messages.append(str(line.get("message", "")))
#             timestamps.append(line["_parsed_timestamp"])

#         unique_templates = list(dict.fromkeys(templates))
#         error_count = sum(
#             level in {"ERROR", "FATAL", "CRITICAL"}
#             for level in levels
#         )
#         warn_count = sum(level == "WARN" for level in levels)

#         incidents.append({
#             "incident_id": int(cluster_id),
#             "line_count": len(lines),
#             "affected_services": sorted(services),
#             "services_count": len(services),
#             "error_count": error_count,
#             "warn_count": warn_count,
#             "time_range": {
#                 "start": min(timestamps).isoformat(),
#                 "end": max(timestamps).isoformat(),
#             },
#             "templates": unique_templates[:10],
#             "sample_messages": cluster_messages[:3],
#             "severity": _infer_incident_severity(
#                 len(lines),
#                 levels,
#                 cluster_messages,
#             ),
#         })

#     incidents.sort(
#         key=lambda incident: (
#             incident["severity"] == "critical",
#             incident["severity"] == "high",
#             incident["error_count"],
#             incident["line_count"],
#         ),
#         reverse=True,
#     )

#     # Reassign IDs in sorted order so the primary incident appears first.
#     for incident_id, incident in enumerate(incidents):
#         incident["incident_id"] = incident_id

#     noise_samples = [
#         str(line.get("message", "")) for line in noise_lines[:5]
#     ]

#     return {
#         "incidents": incidents,
#         "noise_count": len(noise_lines),
#         "noise_samples": noise_samples,
#         "total_anomalous_lines": len(anomalous_lines),
#         "total_clusters": len(incidents),
#         "summary": {
#             "clusters_found": len(incidents),
#             "noise_lines": len(noise_lines),
#             "largest_cluster_size": max(
#                 (incident["line_count"] for incident in incidents),
#                 default=0,
#             ),
#             "eps": eps,
#             "min_samples": min_samples,
#             "window_minutes": window_minutes,
#         },
#     }
