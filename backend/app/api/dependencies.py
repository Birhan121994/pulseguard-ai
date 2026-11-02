
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.services.log_parser import parse_log_text
from backend.app.services.dependency_analyzer import (
    build_cofailure_matrix,
    build_template_trends,
)

router = APIRouter(
    prefix="/api/dependencies",
    tags=["dependencies"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SEED_LOG_PATH = PROJECT_ROOT / "data" / "logs" / "seed_service.log"


class AnalyzeRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)
    window_minutes: int = Field(default=1, ge=1, le=1440)


def load_seed_logs():
    if not SEED_LOG_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail="Seed log file not found",
        )

    try:
        raw_text = SEED_LOG_PATH.read_text(encoding="utf-8")
        parsed = parse_log_text(raw_text)

        if not parsed or not parsed.get("lines"):
            raise HTTPException(
                status_code=400,
                detail="No valid seed log lines found",
            )

        return parsed["lines"]

    except HTTPException:
        raise
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception(
            "Failed to load seed logs"
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to process seed logs",
        ) from exc


@router.post("/cofailure")
def cofailure(request: AnalyzeRequest):
    parsed = parse_log_text(request.raw_text)

    if not parsed or not parsed.get("lines"):
        raise HTTPException(
            status_code=400,
            detail="No valid log lines found",
        )

    return build_cofailure_matrix(
        parsed["lines"],
        request.window_minutes,
    )


@router.post("/templates")
def templates(request: AnalyzeRequest):
    parsed = parse_log_text(request.raw_text)

    if not parsed or not parsed.get("lines"):
        raise HTTPException(
            status_code=400,
            detail="No valid log lines found",
        )

    return build_template_trends(
        parsed["lines"],
        request.window_minutes,
    )


@router.get("/cofailure/seed")
def cofailure_seed(
    window_minutes: int = Query(default=1, ge=1, le=1440),
):
    lines = load_seed_logs()

    return build_cofailure_matrix(
        lines,
        window_minutes,
    )


@router.get("/templates/seed")
def templates_seed(
    window_minutes: int = Query(default=1, ge=1, le=1440),
):
    lines = load_seed_logs()

    return build_template_trends(
        lines,
        window_minutes,
    )
