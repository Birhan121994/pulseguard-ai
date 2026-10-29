from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.log_parser import parse_log_text
from backend.app.services.dependency_analyzer import (
    build_cofailure_matrix,
    build_template_trends,
)

router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])


class AnalyzeRequest(BaseModel):
    raw_text: str
    window_minutes: int = 1


@router.post("/cofailure")
def cofailure(request: AnalyzeRequest):
    """Compute service co-failure matrix from raw logs."""
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")
    parsed = parse_log_text(request.raw_text)
    return build_cofailure_matrix(parsed["lines"], request.window_minutes)


@router.post("/templates")
def templates(request: AnalyzeRequest):
    """Extract per-template time series from raw logs."""
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")
    parsed = parse_log_text(request.raw_text)
    return build_template_trends(parsed["lines"], request.window_minutes)


@router.get("/cofailure/seed")
def cofailure_seed(window_minutes: int = 1):
    from pathlib import Path
    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed log not found")
    parsed = parse_log_text(seed_path.read_text(encoding="utf-8"))
    return build_cofailure_matrix(parsed["lines"], window_minutes)


@router.get("/templates/seed")
def templates_seed(window_minutes: int = 1):
    from pathlib import Path
    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed log not found")
    parsed = parse_log_text(seed_path.read_text(encoding="utf-8"))
    return build_template_trends(parsed["lines"], window_minutes)