from backend.app.services.llm_client import generate_root_cause_explanation


def build_incident_context(incident: dict) -> str:
    """
    Convert an incident cluster (from Step 4) into a compact text context
    suitable for the Groq LLM prompt.

    Keeps the context under ~1500 characters to stay within free-tier limits
    and avoid noise.
    """
    services = ", ".join(incident.get("affected_services", []))
    templates = incident.get("templates", [])
    samples = incident.get("sample_messages", [])
    time_range = incident.get("time_range", {})

    lines = [
        f"Incident summary: {incident.get('line_count', 0)} log lines flagged as anomalous.",
        f"Severity: {incident.get('severity', 'unknown')}.",
        f"Affected services: {services}.",
        f"Time window: {time_range.get('start', '?')} to {time_range.get('end', '?')}.",
        f"Error lines: {incident.get('error_count', 0)}, Warning lines: {incident.get('warn_count', 0)}.",
        "",
        "Log templates observed in this incident:",
    ]

    for i, tmpl in enumerate(templates[:5], 1):
        lines.append(f"  {i}. {tmpl}")

    if samples:
        lines.append("")
        lines.append("Sample log messages (first 3):")
        for msg in samples[:3]:
            lines.append(f"  - {msg}")

    lines.append("")
    lines.append(
        "Based on these patterns, what is the most likely root cause? "
        "Focus on which service or infrastructure component is responsible."
    )

    return "\n".join(lines)


def explain_incident(incident: dict) -> dict:
    """
    Generate a root-cause explanation for a single incident cluster.

    Returns the original incident enriched with:
    - root_cause: plain-English hypothesis (or fallback message)
    - explanation_status: "success" | "fallback" | "error"
    """
    context = build_incident_context(incident)

    try:
        explanation = generate_root_cause_explanation(context)
        if not explanation or not explanation.strip():
            raise ValueError("Empty response from LLM")
        return {
            **incident,
            "root_cause": explanation.strip(),
            "explanation_status": "success",
        }
    except Exception as exc:
        # Graceful fallback: still return the incident, but without LLM text
        fallback = (
            f"Root-cause explanation unavailable ({type(exc).__name__}). "
            f"Incident affects {incident.get('services_count', 0)} service(s) "
            f"with {incident.get('error_count', 0)} errors. "
            f"Review the templates and sample messages above for clues."
        )
        return {
            **incident,
            "root_cause": fallback,
            "explanation_status": "fallback",
        }


def explain_all_incidents(incidents: list[dict], max_incidents: int = 5) -> list[dict]:
    """
    Explain the top N incidents (sorted by severity/size already in Step 4).
    Limits to 5 by default to avoid burning through Groq rate limits.
    """
    explained = []
    for incident in incidents[:max_incidents]:
        explained.append(explain_incident(incident))
    return explained