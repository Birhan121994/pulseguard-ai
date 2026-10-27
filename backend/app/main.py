from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import get_settings
from backend.app.services.llm_client import health_check_llm

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time log anomaly detection & root-cause assistant",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"app": settings.app_name, "status": "running"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_configured": bool(settings.groq_api_key),
    }


@app.get("/health/llm")
def llm_health():
    """Ping Groq to verify the API key and connectivity."""
    ok = health_check_llm()
    return {"llm_reachable": ok}