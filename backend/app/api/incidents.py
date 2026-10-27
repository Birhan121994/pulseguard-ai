from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.app.services.log_parser import parse_log_text
from backend.app.services.anomaly_detector import detect_anomalies
from backend.app.services.incident_clusterer import cluster_anomalous_lines

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


class ClusterRequest(BaseModel):
    raw_text: str
    window_minutes: int = 1
    contamination: float = 0.15
    eps: float = 0.35
    min_samples: int = 2


class Incident(BaseModel):
    incident_id: int
    line_count: int
    affected_services: list[str]
    services_count: int
    error_count: int
    warn_count: int
    time_range: dict
    templates: list[str]
    sample_messages: list[str]
    severity: str


class ClusterResponse(BaseModel):
    incidents: list[Incident]
    noise_count: int
    noise_samples: list[str]
    total_anomalous_lines: int
    total_clusters: int
    summary: dict


@router.post("/cluster", response_model=ClusterResponse)
def cluster(request: ClusterRequest):
    """
    Full pipeline: parse logs → detect anomalies → cluster anomalous lines into incidents.

    This turns scattered anomaly lines into actionable incidents by embedding
    each anomalous message and grouping semantically similar failures with DBSCAN.
    """
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")

    # Step 1: Parse
    parsed = parse_log_text(request.raw_text)
    if parsed["parsed_lines"] == 0:
        raise HTTPException(status_code=400, detail="No lines could be parsed")

    # Step 2: Detect anomalies
    anomaly_result = detect_anomalies(
        parsed["lines"],
        window_minutes=request.window_minutes,
        contamination=request.contamination,
    )

    if not anomaly_result.get("anomaly_windows"):
        return {
            "incidents": [],
            "noise_count": 0,
            "noise_samples": [],
            "total_anomalous_lines": 0,
            "total_clusters": 0,
            "summary": {"message": "No anomalies detected, so no incidents to cluster"},
        }

    # Step 3: Cluster anomalous lines into incidents
    cluster_result = cluster_anomalous_lines(
        anomaly_result["anomaly_windows"],
        parsed["lines"],
        eps=request.eps,
        min_samples=request.min_samples,
    )

    return cluster_result


@router.get("/cluster/seed")
def cluster_seed(
    window_minutes: int = 1,
    contamination: float = 0.15,
    eps: float = 0.35,
    min_samples: int = 2,
):
    """
    Run the full incident clustering pipeline on the built-in seed log file.
    """
    from pathlib import Path

    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed log not found")

    raw_text = seed_path.read_text(encoding="utf-8")
    parsed = parse_log_text(raw_text)

    anomaly_result = detect_anomalies(
        parsed["lines"],
        window_minutes=window_minutes,
        contamination=contamination,
    )

    if not anomaly_result.get("anomaly_windows"):
        return {
            "incidents": [],
            "noise_count": 0,
            "noise_samples": [],
            "total_anomalous_lines": 0,
            "total_clusters": 0,
            "summary": {"message": "No anomalies detected in seed logs"},
        }

    return cluster_anomalous_lines(
        anomaly_result["anomaly_windows"],
        parsed["lines"],
        eps=eps,
        min_samples=min_samples,
    )