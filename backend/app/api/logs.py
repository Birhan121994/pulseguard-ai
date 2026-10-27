from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.app.services.log_parser import parse_log_text

router = APIRouter(prefix="/api/logs", tags=["logs"])


class ParseRequest(BaseModel):
    raw_text: str
    source_name: Optional[str] = "pasted"


class TemplateSummary(BaseModel):
    cluster_id: int
    template: str
    count: int
    sample_service: str
    sample_level: str


class ParsedLine(BaseModel):
    timestamp: str
    level: str
    service: str
    message: str
    template: str
    cluster_id: int
    parameters: list
    change_type: str


class ParseResponse(BaseModel):
    total_lines: int
    parsed_lines: int
    skipped_lines: int
    unique_templates: int
    templates: list[TemplateSummary]
    lines: list[ParsedLine]
    source_name: str


@router.post("/parse", response_model=ParseResponse)
def parse_logs(request: ParseRequest):
    """
    Parse raw log text into structured lines and templates using Drain3.

    The expected log format is:
    `YYYY-MM-DD HH:MM:SS LEVEL [service] message`

    Lines that don't match this format are skipped and counted.
    """
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")

    result = parse_log_text(request.raw_text)
    result["source_name"] = request.source_name
    return result


@router.get("/seed")
def load_seed_logs():
    """
    Load the seed log file and parse it.
    Useful for quick testing without pasting logs.
    """
    from pathlib import Path

    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Seed log file not found. Create data/logs/seed_service.log first."
        )

    raw_text = seed_path.read_text(encoding="utf-8")
    result = parse_log_text(raw_text)
    result["source_name"] = "seed_service.log"
    return result