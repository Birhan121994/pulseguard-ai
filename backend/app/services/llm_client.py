from openai import OpenAI
from backend.app.core.config import get_settings

settings = get_settings()

# Groq is OpenAI-compatible: just change base_url and api_key
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=settings.groq_api_key,
)

DEFAULT_MODEL = "openai/gpt-oss-120b"

def generate_root_cause_explanation(incident_context: str) -> str:
    """
    Given a plain-text summary of an incident (affected services, templates,
    time window, etc.), return a plain-English root-cause hypothesis.
    """
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior DevOps engineer analyzing a production incident. "
                    "Given the incident context, write a concise root-cause hypothesis "
                    "in 2-3 sentences. Be specific about which service or component is likely "
                    "responsible and why. Do not use markdown."
                ),
            },
            {"role": "user", "content": incident_context},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()



def health_check_llm() -> bool:
    """Check Groq connectivity and log the actual failure."""
    import logging

    logger = logging.getLogger(__name__)

    if not settings.groq_api_key:
        logger.error("Groq API key is empty or was not loaded.")
        return False

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=5,
        )
        logger.info("Groq health check succeeded.")
        return True

    except Exception:
        logger.exception("Groq health check failed.")
        return False
