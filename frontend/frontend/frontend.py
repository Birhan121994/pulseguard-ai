
import reflex as rx

from pulseguard.state import PulseGuardState
from pulseguard.components import (
    navbar,
    log_input_card,
    anomaly_timeline_card,
    incident_card,
    risk_gauge,
    cofailure_heatmap_card,     
    template_trend_card,          
)


def dashboard() -> rx.Component:
    return rx.box(
        navbar(),
        rx.container(
            rx.vstack(
                rx.vstack(
                    rx.heading(
                        "Real-time Log Intelligence",
                        size="7",
                        weight="bold",
                        text_align="center",
                    ),
                    rx.text(
                        "Paste logs. Detect anomalies. Cluster incidents. "
                        "Explain root causes. Predict failures.",
                        size="3",
                        color="var(--gray-11)",
                        text_align="center",
                        max_width="600px",
                    ),
                    spacing="2",
                    align="center",
                    padding_y="2rem",
                ),
                log_input_card(),
                rx.cond(
                    PulseGuardState.is_loading,
                    rx.vstack(
                        rx.skeleton(
                            height="200px",
                            width="100%",
                            variant="soft",
                        ),
                        rx.skeleton(
                            height="120px",
                            width="100%",
                            variant="soft",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    rx.cond(
                        PulseGuardState.has_results,
                        rx.vstack(
                            anomaly_timeline_card(),
                            rx.grid(
                                cofailure_heatmap_card(),
                                template_trend_card(),
                                columns=rx.breakpoints(initial="1", lg="2"),
                                spacing="3",
                                width="100%",
                            ),
                            rx.cond(
                                PulseGuardState.show_incidents,
                                rx.vstack(
                                    rx.hstack(
                                        rx.icon("layers", size=20),
                                        rx.heading("Incidents", size="4"),
                                        rx.badge(
                                            PulseGuardState.incident_count.to_string()
                                            + " grouped",
                                            color_scheme="purple",
                                            variant="soft",
                                        ),
                                        spacing="2",
                                        align="center",
                                    ),
                                    rx.grid(
                                        rx.foreach(
                                            PulseGuardState.incidents,
                                            incident_card,
                                        ),
                                        columns=rx.breakpoints(
                                            initial="1",
                                            md="2",
                                        ),
                                        spacing="3",
                                        width="100%",
                                    ),
                                    spacing="3",
                                    width="100%",
                                    align="start",
                                ),
                                rx.fragment(),
                            ),
                            rx.cond(
                                PulseGuardState.show_predictions,
                                rx.vstack(
                                    rx.hstack(
                                        rx.icon("gauge", size=20),
                                        rx.heading(
                                            "Next-Failure Prediction",
                                            size="4",
                                        ),
                                        rx.badge(
                                            "next 3 min",
                                            color_scheme="blue",
                                            variant="soft",
                                        ),
                                        spacing="2",
                                        align="center",
                                    ),
                                    rx.grid(
                                        rx.foreach(
                                            PulseGuardState.predictions,
                                            lambda p: risk_gauge(
                                                p.service,
                                                p.risk_percent,
                                                p.risk_level,
                                            ),
                                        ),
                                        columns=rx.breakpoints(
                                            initial="1",
                                            sm="2",
                                            md="3",
                                        ),
                                        spacing="3",
                                        width="100%",
                                    ),
                                    spacing="3",
                                    width="100%",
                                ),
                                rx.fragment(),
                            ),
                            spacing="5",
                            width="100%",
                            padding_y="1.5rem",
                        ),
                        rx.fragment(),
                    ),
                ),
                spacing="4",
                width="100%",
                max_width="1100px",
                margin="0 auto",
                padding="0 1rem 2rem 1rem",
            ),
            width="100%",
        ),
        min_height="100vh",
        background="var(--color-background)",
        color="var(--gray-12)",
    )


app = rx.App(
    theme=rx.theme(
        appearance="light",
        has_background=True,
        radius="large",
        accent_color="teal",
    ),
    head_components=[
        rx.el.title("PulseGuard AI — Log Anomaly Detection"),
        rx.el.meta(
            name="description",
            content=(
                "Real-time log anomaly detection, incident clustering, "
                "and root-cause explanation."
            ),
        ),
    ],
)

app.add_page(
    dashboard,
    title="PulseGuard AI",
    route="/",
)
