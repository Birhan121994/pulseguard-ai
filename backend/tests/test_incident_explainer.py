from backend.app.services.incident_explainer import build_incident_context, explain_incident


SAMPLE_INCIDENT = {
    "incident_id": 0,
    "line_count": 5,
    "affected_services": ["payment-service", "api-gateway"],
    "services_count": 2,
    "error_count": 5,
    "warn_count": 0,
    "time_range": {"start": "2026-10-27 10:00:15", "end": "2026-10-27 10:00:19"},
    "templates": [
        "Payment failed paymentId=<*> reason=db_pool_exhausted",
        "Upstream timeout service=payment-service status=504",
    ],
    "sample_messages": [
        "Payment failed paymentId=2005 reason=db_pool_exhausted",
        "Payment failed paymentId=2006 reason=db_pool_exhausted",
    ],
    "severity": "critical",
}


def test_context_builder_includes_key_fields():
    context = build_incident_context(SAMPLE_INCIDENT)
    assert "payment-service" in context
    assert "db_pool_exhausted" in context
    assert "critical" in context
    assert "root cause" in context.lower()


def test_context_builder_respects_limits():
    context = build_incident_context(SAMPLE_INCIDENT)
    # Context should be compact (well under 2000 chars)
    assert len(context) < 2000


def test_explain_incident_returns_fallback_on_error(monkeypatch):
    """If the LLM call fails, the incident is still returned with a fallback."""
    def broken_call(context):
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr(
        "backend.app.services.incident_explainer.generate_root_cause_explanation",
        broken_call,
    )

    result = explain_incident(SAMPLE_INCIDENT)
    assert result["explanation_status"] == "fallback"
    assert "unavailable" in result["root_cause"].lower()
    assert result["incident_id"] == 0  # original data preserved