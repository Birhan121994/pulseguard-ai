import pandas as pd
from collections import defaultdict
from backend.app.services.feature_engineer import parsed_lines_to_dataframe


def build_cofailure_matrix(
    parsed_lines: list[dict],
    window_minutes: int = 1,
    min_cofailures: int = 1,
) -> dict:
    """
    Build a service × service co-failure matrix.

    For each time window, collect the set of services that had at least one
    ERROR line. Then for every pair of services in that set, increment their
    co-failure count.
    """
    df = parsed_lines_to_dataframe(parsed_lines)
    if df.empty:
        return {"services": [], "matrix": [], "max_count": 0, "pairs": []}

    errors_df = df[df["level"] == "ERROR"]
    if errors_df.empty:
        return {"services": [], "matrix": [], "max_count": 0, "pairs": []}

    errors_df = errors_df.set_index("timestamp")
    grouped = errors_df.resample(f"{window_minutes}min")

    # For each window, collect the set of services with errors
    window_service_sets = []
    for _, window_df in grouped:
        if not window_df.empty:
            services_in_window = set(window_df["service"].unique())
            if len(services_in_window) >= 2:
                window_service_sets.append(services_in_window)

    # Count co-failures
    pair_counts = defaultdict(int)
    all_services = sorted(set(s for ws in window_service_sets for s in ws))

    for services in window_service_sets:
        services_list = sorted(services)
        for i in range(len(services_list)):
            for j in range(i + 1, len(services_list)):
                pair = (services_list[i], services_list[j])
                pair_counts[pair] += 1

    # Build matrix (symmetric)
    n = len(all_services)
    matrix = [[0] * n for _ in range(n)]
    service_idx = {s: i for i, s in enumerate(all_services)}

    for (s1, s2), count in pair_counts.items():
        i, j = service_idx[s1], service_idx[s2]
        matrix[i][j] = count
        matrix[j][i] = count  # symmetric

    # Extract top pairs for summary
    top_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
    top_pairs_filtered = [
        {"service_a": a, "service_b": b, "count": c}
        for (a, b), c in top_pairs if c >= min_cofailures
    ]

    max_count = max((c for c in pair_counts.values()), default=0)

    return {
        "services": all_services,
        "matrix": matrix,
        "max_count": max_count,
        "pairs": top_pairs_filtered[:10],  # top 10 pairs
    }


def build_template_trends(
    parsed_lines: list[dict],
    window_minutes: int = 1,
) -> dict:
    """
    Build per-template, per-window frequency counts.

    Returns a list of templates with their time series so the frontend
    can let users pick one and plot it.
    """
    df = parsed_lines_to_dataframe(parsed_lines)
    if df.empty:
        return {"templates": []}

    # Build template metadata: cluster_id -> template string, services, level
    template_meta = {}
    for line in parsed_lines:
        tid = line["cluster_id"]
        if tid not in template_meta:
            template_meta[tid] = {
                "cluster_id": tid,
                "template": line["template"],
                "services": set(),
                "levels": set(),
            }
        template_meta[tid]["services"].add(line["service"])
        template_meta[tid]["levels"].add(line["level"])

    # Count per window
    df = df.set_index("timestamp")
    grouped = df.resample(f"{window_minutes}min")

    windows = []
    for window_start, window_df in grouped:
        counts = {}
        if not window_df.empty:
            for tid, count in window_df["cluster_id"].value_counts().items():
                counts[int(tid)] = int(count)
        windows.append({
            "window_start": window_start.isoformat(),
            "counts": counts,
        })

    # Build template list with time series
    templates = []
    for tid, meta in template_meta.items():
        series = []
        for w in windows:
            series.append({
                "window_start": w["window_start"],
                "count": w["counts"].get(tid, 0),
            })
        templates.append({
            "cluster_id": tid,
            "template": meta["template"],
            "services": sorted(meta["services"]),
            "levels": sorted(meta["levels"]),
            "total_count": sum(s["count"] for s in series),
            "series": series,
        })

    # Sort by total count (most frequent first)
    templates.sort(key=lambda x: x["total_count"], reverse=True)

    return {"templates": templates}