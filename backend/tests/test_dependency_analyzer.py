from backend.app.services.log_parser import parse_log_text
from backend.app.services.dependency_analyzer import (
    build_cofailure_matrix,
    build_template_trends,
)


COFAIL_LOGS = """2026-10-27 10:00:01 INFO [api] Request received status=200
2026-10-27 10:00:15 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:16 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:17 ERROR [api] Upstream timeout service=payment
2026-10-27 10:00:25 INFO [api] Request received status=200
2026-10-27 10:00:35 INFO [api] Request received status=200
"""


def test_cofailure_matrix_finds_pair():
    parsed = parse_log_text(COFAIL_LOGS)
    result = build_cofailure_matrix(parsed["lines"], window_minutes=1)
    assert len(result["services"]) >= 2
    assert "payment" in result["services"]
    assert "api" in result["services"]
    assert result["max_count"] >= 1
    assert len(result["pairs"]) >= 1
    pair = result["pairs"][0]
    assert pair["count"] >= 1


def test_cofailure_empty_on_single_service():
    parsed = parse_log_text("2026-10-27 10:00:01 ERROR [svc] failed")
    result = build_cofailure_matrix(parsed["lines"])
    assert result["matrix"] == [] or result["max_count"] == 0


def test_template_trends_returns_series():
    parsed = parse_log_text(COFAIL_LOGS)
    result = build_template_trends(parsed["lines"])
    assert len(result["templates"]) >= 1
    tpl = result["templates"][0]
    assert "series" in tpl
    assert len(tpl["series"]) >= 1
    assert all("count" in s for s in tpl["series"])