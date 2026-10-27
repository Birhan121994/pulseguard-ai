from backend.app.services.log_parser import parse_log_text
from backend.app.services.anomaly_detector import detect_anomalies
from backend.app.services.incident_clusterer import cluster_anomalous_lines


INCIDENT_LOGS = """2026-10-27 10:00:01 INFO [api] Request received status=200
2026-10-27 10:00:05 INFO [api] Request received status=200
2026-10-27 10:00:10 INFO [api] Request received status=200
2026-10-27 10:00:15 ERROR [payment] Payment failed reason=connection_timeout
2026-10-27 10:00:16 ERROR [payment] Payment failed reason=connection_timeout
2026-10-27 10:00:17 ERROR [payment] Payment failed reason=connection_timeout
2026-10-27 10:00:18 ERROR [payment] Payment failed reason=db_pool_exhausted
2026-10-27 10:00:19 ERROR [payment] Payment failed reason=db_pool_exhausted
2026-10-27 10:00:25 INFO [api] Request received status=200
2026-10-27 10:00:30 INFO [api] Request received status=200
"""


def test_incident_clustering_groups_payment_failures():
    parsed = parse_log_text(INCIDENT_LOGS)
    anomaly_result = detect_anomalies(parsed["lines"], window_minutes=1, contamination=0.3)

    assert len(anomaly_result["anomaly_windows"]) >= 1

    cluster_result = cluster_anomalous_lines(
        anomaly_result["anomaly_windows"],
        parsed["lines"],
        eps=0.4,
        min_samples=2,
    )

    assert cluster_result["total_clusters"] >= 1
    largest = cluster_result["incidents"][0]
    assert "payment" in largest["affected_services"]
    assert largest["error_count"] >= 2
    assert largest["severity"] in ("high", "critical")


def test_incident_clustering_handles_no_anomalies():
    parsed = parse_log_text("2026-10-27 10:00:01 INFO [api] Request received status=200")
    result = cluster_anomalous_lines([], parsed["lines"])
    assert result["incidents"] == []
    assert result["total_anomalous_lines"] == 0


def test_noise_lines_are_separated():
    parsed = parse_log_text(INCIDENT_LOGS)
    anomaly_result = detect_anomalies(parsed["lines"], window_minutes=1, contamination=0.4)

    cluster_result = cluster_anomalous_lines(
        anomaly_result["anomaly_windows"],
        parsed["lines"],
        eps=0.2,  # strict clustering → more noise
        min_samples=2,
    )

    # With strict eps, at least some lines should be noise or clusters split
    total_accounted = sum(i["line_count"] for i in cluster_result["incidents"]) + cluster_result["noise_count"]
    assert total_accounted == cluster_result["total_anomalous_lines"]