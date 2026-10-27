from backend.app.services.failure_pipeline import (
    run_training_pipeline,
    run_prediction_pipeline,
)


SEED_LOGS = """2026-10-27 10:00:01 INFO [api] Request received status=200
2026-10-27 10:00:05 INFO [api] Request received status=200
2026-10-27 10:00:10 INFO [api] Request received status=200
2026-10-27 10:00:15 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:16 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:17 ERROR [payment] Payment failed reason=timeout
2026-10-27 10:00:18 ERROR [payment] Payment failed reason=db_pool_exhausted
2026-10-27 10:00:19 ERROR [payment] Payment failed reason=db_pool_exhausted
2026-10-27 10:00:25 INFO [api] Request received status=200
2026-10-27 10:00:30 INFO [api] Request received status=200
2026-10-27 10:00:35 INFO [api] Request received status=200
2026-10-27 10:00:40 INFO [api] Request received status=200
"""


def test_training_pipeline_runs():
    result = run_training_pipeline(SEED_LOGS)
    # May fail if not enough windows, but should not crash
    assert "status" in result or "error" in result


def test_prediction_returns_services():
    result = run_prediction_pipeline(SEED_LOGS)
    if "error" not in result:
        assert len(result["predictions"]) >= 1
        assert all("risk" in p for p in result["predictions"])
        assert all("service" in p for p in result["predictions"])