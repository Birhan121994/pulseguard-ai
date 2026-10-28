import reflex as rx
import httpx
import plotly.graph_objects as go
from typing import Optional


API_BASE = "http://localhost:8000"


class Incident(rx.Base):
    severity: str = "low"
    line_count: int = 0
    services_count: int = 0
    affected_services: list[str] = []
    root_cause: str = "No root cause available."
    templates: list[str] = []
    sample_messages: list[str] = []


class Prediction(rx.Base):
    service: str = "Unknown service"
    risk: Optional[float] = None
    risk_percent: Optional[float] = None
    risk_level: str = "unknown"
    message: Optional[str] = None


class PulseGuardState(rx.State):
    # Input
    raw_logs: str = ""
    is_loading: bool = False
    error_message: str = ""

    # Typed analysis results
    anomaly_windows: list[dict] = []
    incidents: list[Incident] = []
    predictions: list[Prediction] = []
    summary: dict = {}

    # UI state
    show_incidents: bool = False
    show_predictions: bool = False

    @rx.var(cache=True)
    def has_results(self) -> bool:
        return bool(self.anomaly_windows or self.incidents)

    @rx.var(cache=True)
    def anomaly_count(self) -> int:
        if "anomaly_windows" in self.summary:
            try:
                return int(self.summary["anomaly_windows"])
            except (TypeError, ValueError):
                pass

        return sum(
            1
            for window in self.anomaly_windows
            if window.get("is_anomaly", False)
        )

    @rx.var(cache=True)
    def incident_count(self) -> int:
        return len(self.incidents)

    @rx.var(cache=True)
    def anomaly_timeline_figure(self) -> go.Figure:
        if not self.anomaly_windows:
            fig = go.Figure()
            fig.update_layout(
                title="Anomaly Timeline",
                template="plotly_white",
                height=300,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            return fig

        timestamps = [
            window["window_start"]
            for window in self.anomaly_windows
        ]
        error_counts = [
            window["error_count"]
            for window in self.anomaly_windows
        ]
        colors = [
            "#ef4444" if window.get("is_anomaly", False)
            else "#22c55e"
            for window in self.anomaly_windows
        ]
        sizes = [
            18 if window.get("is_anomaly", False) else 8
            for window in self.anomaly_windows
        ]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=error_counts,
                mode="markers+lines",
                marker=dict(
                    color=colors,
                    size=sizes,
                    line=dict(width=1, color="#1e293b"),
                ),
                line=dict(
                    color="#64748b",
                    width=1,
                    dash="dot",
                ),
                text=[
                    f"Severity: {window.get('severity', 'unknown')}"
                    for window in self.anomaly_windows
                ],
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Errors: %{y}<br>"
                    "%{text}<extra></extra>"
                ),
                name="Error Count",
            )
        )

        fig.update_layout(
            title="Anomaly Timeline",
            xaxis_title="Time Window",
            yaxis_title="Error Count",
            template="plotly_white",
            height=300,
            margin=dict(l=20, r=20, t=40, b=20),
            showlegend=False,
        )
        return fig

    @rx.event
    async def analyze_logs(self):
        if not self.raw_logs.strip():
            self.error_message = "Please paste some log lines first."
            return

        self.is_loading = True
        self.error_message = ""
        self.anomaly_windows = []
        self.incidents = []
        self.predictions = []
        self.summary = {}
        self.show_incidents = False
        self.show_predictions = False

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1. Detect anomalies
                anomaly_resp = await client.post(
                    f"{API_BASE}/api/anomalies/detect",
                    json={
                        "raw_text": self.raw_logs,
                        "window_minutes": 1,
                        "contamination": 0.15,
                    },
                )

                if anomaly_resp.status_code != 200:
                    self.error_message = (
                        f"Anomaly detection failed: {anomaly_resp.text}"
                    )
                    return

                anomaly_data = anomaly_resp.json()
                self.anomaly_windows = anomaly_data.get("windows", [])
                self.summary = anomaly_data.get("summary", {})

                # 2. Cluster incidents and explain root causes
                explain_resp = await client.post(
                    f"{API_BASE}/api/incidents/explain",
                    json={
                        "raw_text": self.raw_logs,
                        "window_minutes": 1,
                        "contamination": 0.15,
                        "eps": 0.35,
                        "min_samples": 2,
                        "max_incidents": 5,
                    },
                )

                if explain_resp.status_code == 200:
                    explain_data = explain_resp.json()
                    self.incidents = [
                        Incident(**item)
                        for item in explain_data.get("incidents", [])
                    ]
                    self.show_incidents = bool(self.incidents)
                else:
                    self.error_message = (
                        "Incident analysis warning: "
                        f"{explain_resp.text}"
                    )

                # 3. Predict potential failures
                predict_resp = await client.post(
                    f"{API_BASE}/api/predict/failure",
                    json={"raw_text": self.raw_logs},
                )

                if predict_resp.status_code == 200:
                    predict_data = predict_resp.json()
                    self.predictions = [
                        Prediction(**item)
                        for item in predict_data.get("predictions", [])
                    ]
                    self.show_predictions = bool(self.predictions)
                else:
                    warning = (
                        "Failure prediction warning: "
                        f"{predict_resp.text}"
                    )
                    self.error_message = (
                        f"{self.error_message}\n{warning}"
                        if self.error_message
                        else warning
                    )

        except httpx.RequestError as exc:
            self.error_message = (
                "Cannot connect to the backend. "
                f"Check that the API is running at {API_BASE}. "
                f"Details: {exc}"
            )

        except Exception as exc:
            self.error_message = (
                f"Backend error: {type(exc).__name__}: {exc}"
            )

        finally:
            self.is_loading = False

    @rx.event
    def load_seed_demo(self):
        self.raw_logs = """2026-10-27 10:00:01 INFO [api-gateway] Request received path=/api/orders status=200
2026-10-27 10:00:05 INFO [api-gateway] Request received path=/api/users status=200
2026-10-27 10:00:10 INFO [order-service] Processing order orderId=1001
2026-10-27 10:00:15 ERROR [payment-service] Payment failed reason=connection_timeout
2026-10-27 10:00:16 ERROR [payment-service] Payment failed reason=connection_timeout
2026-10-27 10:00:17 ERROR [payment-service] Payment failed reason=connection_timeout
2026-10-27 10:00:18 ERROR [payment-service] Payment failed reason=db_pool_exhausted
2026-10-27 10:00:19 ERROR [payment-service] Payment failed reason=db_pool_exhausted
2026-10-27 10:00:25 INFO [api-gateway] Request received path=/api/orders status=200
2026-10-27 10:00:30 INFO [api-gateway] Request received path=/api/users status=200
2026-10-27 10:00:35 INFO [api-gateway] Request received path=/api/orders status=200
2026-10-27 10:00:40 INFO [api-gateway] Request received path=/api/users status=200"""
        self.error_message = ""



def format_risk(risk_percent):
    if risk_percent is None:
        return "Unknown"
    return f"{risk_percent:.1f}%"
