
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.log_parser import parse_log_text
from backend.app.services.anomaly_detector import detect_anomalies


router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])

# Resolve the project-relative seed file from a predictable location.
# Adjust this if your repository uses a different root layout.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SEED_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "seed_service.log"


class DetectRequest(BaseModel):
    raw_text: str = Field(
        ...,
        min_length=1,
        description="Raw application log text",
    )
    window_minutes: int = Field(default=1, ge=1, le=1440)
    contamination: float = Field(default=0.15, gt=0, lt=0.5)


class WindowResult(BaseModel):
    window_start: str
    total_logs: int
    error_count: int
    warn_count: int
    error_rate: float
    unique_templates: int
    unique_services: int
    max_template_freq: int
    template_entropy: float
    is_anomaly: bool
    anomaly_score: float
    severity: str


class DetectSummary(BaseModel):
    total_windows: int
    anomaly_windows: int
    anomaly_rate: float
    window_minutes: int
    contamination: float
    detector: str = "none"
    model_used: bool = False
    rule_based_windows: int = 0
    services_in_anomalies: list[str] = []
    message: str | None = None


class DetectResponse(BaseModel):
    windows: list[WindowResult]
    anomaly_windows: list[WindowResult]
    summary: DetectSummary


def _run_detection(
    raw_text: str,
    window_minutes: int,
    contamination: float,
) -> dict[str, Any]:
    if not raw_text or not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail="raw_text must not be empty",
        )

    try:
        parsed = parse_log_text(raw_text)

        if not parsed or not parsed.get("lines"):
            raise HTTPException(
                status_code=400,
                detail="No lines could be parsed. Check the log format.",
            )

        result = detect_anomalies(
            parsed["lines"],
            window_minutes=window_minutes,
            contamination=contamination,
        )

        return result

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Keep internal exception details out of public API responses.
        import logging

        logging.getLogger(__name__).exception(
            "Anomaly detection request failed"
        )
        raise HTTPException(
            status_code=500,
            detail="Anomaly detection failed unexpectedly",
        ) from exc


@router.post("/detect", response_model=DetectResponse)
def detect(request: DetectRequest) -> dict[str, Any]:
    """
    Parse logs, aggregate time windows, and detect anomalies.
    """
    return _run_detection(
        raw_text=request.raw_text,
        window_minutes=request.window_minutes,
        contamination=request.contamination,
    )


@router.get("/detect/seed", response_model=DetectResponse)
def detect_seed(
    window_minutes: int = Query(default=1, ge=1, le=1440),
    contamination: float = Query(default=0.15, gt=0, lt=0.5),
) -> dict[str, Any]:
    """
    Run anomaly detection on the built-in seed log file.
    """
    if not SEED_LOG_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Seed log not found: {SEED_LOG_PATH.name}",
        )

    try:
        raw_text = SEED_LOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        import logging

        logging.getLogger(__name__).exception(
            "Could not read seed log file"
        )
        raise HTTPException(
            status_code=500,
            detail="Could not read the seed log file",
        ) from exc

    return _run_detection(
        raw_text=raw_text,
        window_minutes=window_minutes,
        contamination=contamination,
    )
