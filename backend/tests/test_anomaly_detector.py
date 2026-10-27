from backend.app.services.log_parser import parse_log_text
from backend.app.services.anomaly_detector import detect_anomalies


SPIKE_LOGS = """2026-10-27 10:00:01 INFO [api] Request received status=200
2026-10-27 10:00:05 INFO [api] Request received status=200
2026-10-27 10:00:10 INFO [api] Request received status=200
2026-10-27 10:00:15 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:16 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:17 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:18 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:19 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:25 INFO [api] Request received status=200
2026-10-27 10:00:30 INFO [api] Request received status=200
2026-10-27 10:00:35 INFO [api] Request received status=200
2026-10-27 10:00:40 INFO [api] Request received status=200
"""


def test_detector_flags_error_burst():
    parsed = parse_log_text(SPIKE_LOGS)
    result = detect_anomalies(parsed["lines"], window_minutes=1, contamination=0.3)

    assert len(result["windows"]) >= 1
    assert len(result["anomaly_windows"]) >= 1

    # The anomaly window should have errors
    anomaly = result["anomaly_windows"][0]
    assert anomaly["error_count"] > 0
    assert anomaly["severity"] in ("medium", "high", "critical")


def test_detector_returns_empty_for_empty_input():
    result = detect_anomalies([], window_minutes=1)
    assert "error" in result
    assert result["windows"] == []


def test_severity_mapping():
    from backend.app.services.anomaly_detector import _score_to_severity
    assert _score_to_severity(-0.2) == "critical"
    assert _score_to_severity(-0.1) == "high"
    assert _score_to_severity(-0.02) == "medium"
    assert _score_to_severity(0.1) == "normal"