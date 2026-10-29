
import reflex as rx
from pulseguard.state import PulseGuardState


def navbar() -> rx.Component:
    return rx.hstack(
        rx.hstack(
            rx.icon("shield-check", size=28, color="var(--accent-9)"),
            rx.heading("PulseGuard AI", size="6", weight="bold"),
            spacing="2",
            align="center",
        ),
        rx.spacer(),
        rx.hstack(
            rx.badge(
                "Observability",
                color_scheme="gray",
                variant="soft",
                radius="full",
            ),
            rx.color_mode.button(),
            spacing="3",
            align="center",
        ),
        width="100%",
        padding="1rem 2rem",
        border_bottom="1px solid var(--gray-a5)",
        background="var(--color-background)",
        position="sticky",
        top="0",
        z_index="100",
        backdrop_filter="blur(12px)",
    )


def log_input_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("file-text", size=20),
                rx.heading("Paste Your Logs", size="4"),
                rx.spacer(),
                rx.button(
                    "Load Demo",
                    variant="soft",
                    size="2",
                    on_click=PulseGuardState.load_seed_demo,
                    icon="play",
                ),
                width="100%",
                align="center",
            ),
            rx.text_area(
                placeholder=(
                    "Paste server/application logs here...\n\n"
                    "Expected format:\n"
                    "2026-10-27 10:00:01 INFO [service] message"
                ),
                value=PulseGuardState.raw_logs,
                on_change=PulseGuardState.set_raw_logs,
                height="160px",
                font_family="monospace",
                font_size="13px",
                width="100%",
            ),
            rx.hstack(
                rx.cond(
                    PulseGuardState.error_message != "",
                    rx.callout(
                        PulseGuardState.error_message,
                        icon="triangle-alert",
                        color_scheme="red",
                        size="1",
                    ),
                    rx.fragment(),
                ),
                rx.spacer(),
                rx.button(
                    "Analyze Logs",
                    on_click=PulseGuardState.analyze_logs,
                    loading=PulseGuardState.is_loading,
                    disabled=PulseGuardState.is_loading,
                    size="3",
                    icon="scan-search",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        size="3",
    )


def anomaly_timeline_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("activity", size=20),
                rx.heading("Anomaly Timeline", size="4"),
                rx.spacer(),
                rx.badge(
                    PulseGuardState.anomaly_count.to_string()
                    + " anomalies",
                    color_scheme="red",
                    variant="soft",
                ),
                width="100%",
                align="center",
            ),
            rx.color_mode_cond(
                light=rx.plotly(
                    data=PulseGuardState.anomaly_timeline_figure,
                    width="100%",
                ),
                dark=rx.plotly(
                    data=PulseGuardState.anomaly_timeline_figure,
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        size="3",
    )


def incident_card(incident) -> rx.Component:
    severity_color = rx.cond(
        incident.severity == "critical",
        "red",
        rx.cond(
            incident.severity == "high",
            "orange",
            rx.cond(
                incident.severity == "medium",
                "yellow",
                "gray",
            ),
        ),
    )

    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.badge(
                    incident.severity,
                    color_scheme=severity_color,
                    variant="solid",
                    size="1",
                ),
                rx.text(
                    incident.line_count.to_string() + " lines",
                    size="1",
                    color="var(--gray-11)",
                ),
                rx.spacer(),
                rx.text(
                    incident.services_count.to_string()
                    + " service(s)",
                    size="1",
                    color="var(--gray-11)",
                ),
                width="100%",
                align="center",
            ),
            rx.heading(
                rx.cond(
                    incident.affected_services.length() > 0,
                    incident.affected_services[0],
                    "Unknown Service",
                ),
                size="3",
            ),
            rx.text(
                incident.root_cause,
                size="2",
                color="var(--gray-11)",
                line_height="1.6",
            ),
            rx.accordion.root(
                rx.accordion.item(
                    header=rx.text("Templates & Samples", size="1"),
                    content=rx.vstack(
                        rx.foreach(
                            incident.templates,
                            lambda template: rx.code(
                                template,
                                size="1",
                                width="100%",
                            ),
                        ),
                        rx.divider(),
                        rx.foreach(
                            incident.sample_messages,
                            lambda message: rx.text(
                                message,
                                size="1",
                                color="var(--gray-10)",
                                font_family="monospace",
                            ),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                collapsible=True,
                width="100%",
                variant="soft",
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        size="2",
    )



def risk_gauge(
    service: str,
    risk_percent: float,
    level: str,
) -> rx.Component:
    color = rx.cond(
        level == "critical",
        "red",
        rx.cond(
            level == "high",
            "orange",
            rx.cond(
                level == "medium",
                "yellow",
                "green",
            ),
        ),
    )

    # Convert the percentage to an integer for Reflex Progress.
    progress_value = risk_percent.to(int)

    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    service,
                    size="1",
                    weight="medium",
                ),
                rx.spacer(),
                rx.badge(
                    level,
                    color_scheme=color,
                    variant="soft",
                    size="1",
                ),
                width="100%",
            ),
            rx.progress(
                value=progress_value,
                color_scheme=color,
                size="2",
                width="100%",
            ),
            rx.text(
                risk_percent.to_string() + "% failure risk",
                size="1",
                color="var(--gray-10)",
            ),
            spacing="1",
            width="100%",
        ),
        padding="0.75rem",
        border_radius="var(--radius-3)",
        border="1px solid var(--gray-a4)",
        width="100%",
    )


def cofailure_heatmap_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("git-merge", size=20),
                rx.heading("Service Co-Failure Heatmap", size="4"),
                rx.spacer(),
                rx.badge(
                    f"{PulseGuardState.cofailure_pairs.length()} pairs",
                    color_scheme="red",
                    variant="soft",
                ),
                width="100%",
                align="center",
            ),
            rx.text(
                "Darker cells indicate services that fail together more often.",
                size="1",
                color="var(--gray-10)",
            ),
            rx.plotly(data=PulseGuardState.cofailure_figure, width="100%"),
            rx.cond(
                PulseGuardState.cofailure_pairs.length() > 0,
                rx.vstack(
                    rx.text("Top co-failing pairs:", size="1", weight="medium"),
                    rx.foreach(
                        PulseGuardState.cofailure_pairs[:3],
                        lambda p: rx.hstack(
                            rx.badge(p["service_a"], variant="soft", size="1"),
                            rx.text("↔", size="1"),
                            rx.badge(p["service_b"], variant="soft", size="1"),
                            rx.spacer(),
                            rx.text(f"{p['count']}x", size="1", color="var(--gray-10)"),
                            width="100%",
                        ),
                    ),
                    spacing="1",
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        size="3",
    )




def template_trend_card() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("trending-up", size=20),
                rx.heading("Template Trend Explorer", size="4"),
                rx.spacer(),
                rx.select(
                    PulseGuardState.template_options,
                    value=PulseGuardState.selected_template_label,
                    on_change=PulseGuardState.select_template,
                    placeholder="Select a template...",
                    width="300px",
                ),
                width="100%",
                align="center",
            ),
            rx.text(
                "Click a template to see its frequency over time. "
                "Red bands mark anomalous windows.",
                size="1",
                color="var(--gray-10)",
            ),
            rx.plotly(
                data=PulseGuardState.template_trend_figure,
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
        size="3",
    )
