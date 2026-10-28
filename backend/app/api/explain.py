from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.app.services.log_parser import parse_log_text
from backend.app.services.anomaly_detector import detect_anomalies
from backend.app.services.incident_clusterer import cluster_anomalous_lines
from backend.app.services.incident_explainer import explain_all_incidents

router = APIRouter(prefix="/api/incidents", tags=["explain"])


class ExplainRequest(BaseModel):
    raw_text: str
    window_minutes: int = 1
    contamination: float = 0.15
    eps: float = 0.35
    min_samples: int = 2
    max_incidents: int = 5


class ExplainedIncident(BaseModel):
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
    root_cause: str
    explanation_status: str


class ExplainResponse(BaseModel):
    incidents: list[ExplainedIncident]
    noise_count: int
    total_anomalous_lines: int
    total_clusters: int
    explained_count: int
    summary: dict


def _run_pipeline(raw_text: str, req) -> dict:
    """Shared pipeline: parse → detect → cluster → explain."""
    parsed = parse_log_text(raw_text)
    if parsed["parsed_lines"] == 0:
        raise HTTPException(status_code=400, detail="No lines could be parsed")

    anomaly_result = detect_anomalies(
        parsed["lines"],
        window_minutes=req.window_minutes,
        contamination=req.contamination,
    )

    if not anomaly_result.get("anomaly_windows"):
        return {
            "incidents": [],
            "noise_count": 0,
            "total_anomalous_lines": 0,
            "total_clusters": 0,
            "explained_count": 0,
            "summary": {"message": "No anomalies detected, so no incidents to explain"},
        }

    cluster_result = cluster_anomalous_lines(
        anomaly_result["anomaly_windows"],
        parsed["lines"],
        eps=req.eps,
        min_samples=req.min_samples,
    )

    explained = explain_all_incidents(
        cluster_result["incidents"],
        max_incidents=req.max_incidents,
    )

    return {
        "incidents": explained,
        "noise_count": cluster_result["noise_count"],
        "total_anomalous_lines": cluster_result["total_anomalous_lines"],
        "total_clusters": cluster_result["total_clusters"],
        "explained_count": len(explained),
        "summary": {
            "pipeline": "parse → detect → cluster → explain",
            "llm_model": "llama-3.3-70b-versatile",
            "explained_incidents": len(explained),
        },
    }


@router.post("/explain", response_model=ExplainResponse)
def explain(request: ExplainRequest):
    """
    Full pipeline with LLM root-cause explanation.

    Runs anomaly detection, clusters anomalous lines into incidents,
    then asks Groq's Llama model to generate a plain-English root cause
    for the top incidents.
    """
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")
    return _run_pipeline(request.raw_text, request)


@router.get("/explain/seed")
def explain_seed(
    window_minutes: int = 1,
    contamination: float = 0.15,
    eps: float = 0.35,
    min_samples: int = 2,
    max_incidents: int = 5,
):
    """
    One-click demo: run the full pipeline with LLM explanation on seed logs.
    """
    from pathlib import Path

    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed log not found")

    raw_text = seed_path.read_text(encoding="utf-8")

    # Reuse a simple namespace for the shared pipeline
    class Req:
        pass

    req = Req()
    req.window_minutes = window_minutes
    req.contamination = contamination
    req.eps = eps
    req.min_samples = min_samples
    req.max_incidents = max_incidents

    return _run_pipeline(raw_text, req)