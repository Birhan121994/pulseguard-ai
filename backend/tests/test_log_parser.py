from backend.app.services.log_parser import parse_log_text


SAMPLE_LOGS = """2026-10-27 10:00:01 INFO [api-gateway] Request received path=/api/orders status=200
2026-10-27 10:00:02 INFO [api-gateway] Request received path=/api/users status=200
2026-10-27 10:00:03 ERROR [payment-service] Payment failed paymentId=2001 reason=timeout
2026-10-27 10:00:04 ERROR [payment-service] Payment failed paymentId=2002 reason=timeout
2026-10-27 10:00:05 INFO [order-service] Order confirmed orderId=1001
"""


def test_parse_returns_all_lines():
    result = parse_log_text(SAMPLE_LOGS)
    assert result["parsed_lines"] == 5
    assert result["skipped_lines"] == 0


def test_identical_patterns_share_template():
    result = parse_log_text(SAMPLE_LOGS)
    payment_lines = [l for l in result["lines"] if l["service"] == "payment-service"]
    assert len(payment_lines) == 2
    assert payment_lines[0]["cluster_id"] == payment_lines[1]["cluster_id"]


def test_different_patterns_have_different_templates():
    result = parse_log_text(SAMPLE_LOGS)
    gateway_lines = [l for l in result["lines"] if l["service"] == "api-gateway"]
    assert len(gateway_lines) == 2
    assert gateway_lines[0]["cluster_id"] == gateway_lines[1]["cluster_id"]

    order_lines = [l for l in result["lines"] if l["service"] == "order-service"]
    assert order_lines[0]["cluster_id"] != gateway_lines[0]["cluster_id"]


def test_invalid_lines_are_skipped():
    result = parse_log_text("this is not a valid log line\n2026-10-27 10:00:01 INFO [svc] valid message")
    assert result["skipped_lines"] == 1
    assert result["parsed_lines"] == 1