from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.failure_pipeline import (
    run_training_pipeline,
    run_prediction_pipeline,
)

router = APIRouter(prefix="/api/predict", tags=["prediction"])


class TrainRequest(BaseModel):
    raw_text: str



class PredictionItem(BaseModel):
    service: str
    risk: float | None = None
    risk_percent: float | None = None
    risk_level: str
    message: str | None = None



class PredictResponse(BaseModel):
    predictions: list[PredictionItem]
    window_start: str | None = None
    horizon_minutes: int
    model_loaded: bool


@router.post("/train")
def train(request: TrainRequest):
    """Train the XGBoost failure predictor on provided logs."""
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")

    result = run_training_pipeline(request.raw_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/failure", response_model=PredictResponse)
def predict_failure(request: TrainRequest):
    """Predict per-service failure risk for the next 3 minutes."""
    if not request.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text is empty")

    result = run_prediction_pipeline(request.raw_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/train/seed")
def train_seed():
    """Train on seed logs and return model metrics."""
    from pathlib import Path

    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed log not found")

    raw_text = seed_path.read_text(encoding="utf-8")
    result = run_training_pipeline(raw_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/failure/seed")
def predict_seed():
    """One-click: predict failure risk from seed logs."""
    from pathlib import Path

    seed_path = Path("data/logs/seed_service.log")
    if not seed_path.exists():
        raise HTTPException(status_code=404, detail="Seed log not found")

    raw_text = seed_path.read_text(encoding="utf-8")
    result = run_prediction_pipeline(raw_text)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result