"""Shared Plotly chart builders for the Streamlit dashboard.

Centralizes color palette, layout, and formatting so every page looks like
one consistent product rather than each page picking its own chart style.
The palette is a fixed-order, colorblind-validated categorical set (not
chosen by eye) — do not reorder it or add ad hoc colors per chart.

Every function here takes already-aggregated data (from src.metrics /
src.segmentation) and returns a plotly.graph_objects.Figure. No business
logic lives here — pages call src.metrics/src.segmentation for numbers and
this module only for presentation.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Fixed-order categorical palette — colorblind-validated, never cycle/reorder.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]
PRIMARY = CATEGORICAL[0]
MUTED = "#c3c2b7"        # de-emphasized series (e.g. partial time periods)
GRIDLINE = "#e1e0d9"
AXIS_INK = "#898781"
TEXT_INK = "#52514e"
FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"
CHART_HEIGHT = 380


def _base_layout(fig: go.Figure, height: int = CHART_HEIGHT) -> go.Figure:
    """Apply shared typography, spacing, and chrome to any figure."""
    fig.update_layout(
        font=dict(family=FONT_FAMILY, color=TEXT_INK, size=13),
        height=height,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="white", font_size=12, font_family=FONT_FAMILY),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, title=None),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRIDLINE, tickfont=dict(color=AXIS_INK))
    fig.update_yaxes(showgrid=True, gridcolor=GRIDLINE, zeroline=False, tickfont=dict(color=AXIS_INK))
    return fig


def monthly_revenue_chart(monthly: pd.DataFrame, partial_months: set[str]) -> go.Figure:
    """Bar chart of monthly delivered-order revenue. Partial months (dataset
    boundary periods with incomplete data) are shown in a muted color rather
    than excluded outright, so the trend isn't visually implied to start/end
    somewhere it didn't."""
    colors = [MUTED if mth in partial_months else PRIMARY for mth in monthly["month"]]
    fig = go.Figure(go.Bar(
        x=monthly["month"], y=monthly["revenue"], marker_color=colors,
        hovertemplate="%{x}<br>Revenue: R$ %{y:,.0f}<extra></extra>",
    ))
    fig.update_yaxes(title="Revenue (R$)", tickformat=",.0f")
    fig.update_xaxes(title=None, tickangle=-45)
    return _base_layout(fig)


def horizontal_bar_chart(
    df: pd.DataFrame, label_col: str, value_col: str, value_title: str,
    hover_suffix: str = "", top_n: int = 10,
) -> go.Figure:
    """Horizontal bar chart, largest value on top — the standard form for
    ranked categorical comparisons (categories, states)."""
    top = df.nlargest(top_n, value_col).sort_values(value_col)
    fig = go.Figure(go.Bar(
        x=top[value_col], y=top[label_col], orientation="h", marker_color=PRIMARY,
        hovertemplate=f"%{{y}}<br>{value_title}: %{{x:,.0f}}{hover_suffix}<extra></extra>",
    ))
    fig.update_xaxes(title=value_title, tickformat=",.0f")
    fig.update_yaxes(title=None)
    return _base_layout(fig, height=max(280, 28 * len(top)))


def review_score_distribution_chart(orders_analytics: pd.DataFrame) -> go.Figure:
    """Bar chart of the 1-5 review score distribution among reviewed orders."""
    counts = (
        orders_analytics.loc[orders_analytics["is_delivered"], "avg_review_score"]
        .dropna().round().astype(int).value_counts().sort_index()
    )
    fig = go.Figure(go.Bar(
        x=counts.index.astype(str), y=counts.values, marker_color=PRIMARY,
        hovertemplate="%{x} stars<br>%{y:,} orders<extra></extra>",
    ))
    fig.update_xaxes(title="Review score")
    fig.update_yaxes(title="Orders", tickformat=",.0f")
    return _base_layout(fig)


def delay_bucket_review_chart(bucket_summary: pd.DataFrame) -> go.Figure:
    """Bar chart of average review score by delivery-delay bucket — the key
    chart showing the (associational, not causal) relationship between
    lateness and satisfaction."""
    fig = go.Figure(go.Bar(
        x=bucket_summary["delay_bucket"], y=bucket_summary["avg_review_score"],
        marker_color=PRIMARY, text=bucket_summary["avg_review_score"].round(2),
        textposition="outside",
        hovertemplate="%{x}<br>Avg review score: %{y:.2f}<br>%{customdata:,} orders<extra></extra>",
        customdata=bucket_summary["orders"],
    ))
    fig.update_yaxes(title="Average review score", range=[0, 5.3])
    fig.update_xaxes(title=None)
    return _base_layout(fig, height=340)


def on_time_split_chart(on_time_rate: float) -> go.Figure:
    """Single-row 100%-stacked bar showing on-time vs late share — a compact
    alternative to a KPI card when the split itself is the point."""
    late_rate = 1 - on_time_rate
    fig = go.Figure()
    fig.add_bar(x=[on_time_rate * 100], y=[""], orientation="h", name="On-time",
                marker_color=PRIMARY, hovertemplate=f"On-time: {on_time_rate*100:.1f}%<extra></extra>")
    fig.add_bar(x=[late_rate * 100], y=[""], orientation="h", name="Late",
                marker_color=MUTED, hovertemplate=f"Late: {late_rate*100:.1f}%<extra></extra>")
    fig.update_layout(barmode="stack", showlegend=True)
    fig.update_xaxes(title=None, range=[0, 100], ticksuffix="%")
    fig.update_yaxes(title=None, showticklabels=False, showgrid=False)
    return _base_layout(fig, height=110)


def cohort_heatmap(matrix: pd.DataFrame, max_periods: int = 18) -> go.Figure:
    """Cohort retention heatmap. NaN cells (calendar months that haven't
    happened yet for that cohort) render as blank — never as 0% — since
    Plotly's Heatmap leaves NaN unfilled by default."""
    display = matrix.iloc[:, :max_periods]
    fig = go.Figure(go.Heatmap(
        z=display.values * 100, x=[f"M{c}" for c in display.columns], y=display.index,
        colorscale=[[i / (len(SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(SEQUENTIAL_BLUE)],
        hoverongaps=False, zmin=0, zmax=100,
        hovertemplate="Cohort %{y}, %{x}<br>Retention: %{z:.1f}%<extra></extra>",
        colorbar=dict(title="%", ticksuffix="%"),
    ))
    fig.update_xaxes(title=None, side="top")
    fig.update_yaxes(title=None, autorange="reversed")
    return _base_layout(fig, height=max(320, 26 * len(display)))


def segment_comparison_chart(segment_summary: pd.DataFrame) -> go.Figure:
    """Grouped horizontal bar comparing % of customers vs % of revenue per
    segment — the core "count is not value" chart for Customer Intelligence."""
    ordered = segment_summary.sort_values("pct_of_revenue")
    fig = go.Figure()
    fig.add_bar(y=ordered["segment"], x=ordered["pct_of_customers"], name="% of customers",
                orientation="h", marker_color=CATEGORICAL[0],
                hovertemplate="%{y}<br>%{x:.1f}%% of customers<extra></extra>")
    fig.add_bar(y=ordered["segment"], x=ordered["pct_of_revenue"], name="% of revenue",
                orientation="h", marker_color=CATEGORICAL[1],
                hovertemplate="%{y}<br>%{x:.1f}%% of revenue<extra></extra>")
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Share (%)", ticksuffix="%")
    fig.update_yaxes(title=None)
    return _base_layout(fig, height=320)


def frequency_distribution_chart(customer_summary: pd.DataFrame) -> go.Figure:
    """Bar chart of delivered-order count per customer (log y-axis — the
    long tail beyond 2-3 orders is very thin)."""
    counts = customer_summary["delivered_order_count"].value_counts().sort_index()
    fig = go.Figure(go.Bar(
        x=counts.index.astype(str), y=counts.values, marker_color=PRIMARY,
        hovertemplate="%{x} orders<br>%{y:,} customers<extra></extra>",
    ))
    fig.update_yaxes(title="Customers (log scale)", type="log")
    fig.update_xaxes(title="Delivered orders per customer")
    return _base_layout(fig)


def retention_window_chart(window_results: pd.DataFrame) -> go.Figure:
    """Bar chart of eligibility-adjusted retention rate by window."""
    fig = go.Figure(go.Bar(
        x=[f"{d}-day" for d in window_results["window_days"]],
        y=window_results["retention_rate"] * 100,
        marker_color=PRIMARY, text=(window_results["retention_rate"] * 100).round(2),
        textposition="outside",
        hovertemplate="%{x} window<br>%{y:.2f}%% retention<extra></extra>",
    ))
    fig.update_yaxes(title="Retention rate (%)")
    fig.update_xaxes(title=None)
    return _base_layout(fig, height=300)


def delivery_time_histogram(eligible_orders: pd.DataFrame) -> go.Figure:
    """Histogram of delivery time (days) among timing-eligible delivered orders."""
    fig = go.Figure(go.Histogram(
        x=eligible_orders["delivery_days"], nbinsx=50, marker_color=PRIMARY,
        hovertemplate="%{x} days<br>%{y:,} orders<extra></extra>",
    ))
    fig.update_xaxes(title="Delivery time (days)")
    fig.update_yaxes(title="Orders", tickformat=",.0f")
    return _base_layout(fig, height=320)


def state_operations_chart(state_summary: pd.DataFrame, min_orders: int = 100, top_n: int = 12) -> go.Figure:
    """Horizontal bar of on-time delivery rate by state, restricted to
    states with enough volume for the rate to be meaningful."""
    reliable = state_summary[state_summary["timing_eligible_orders"] >= min_orders]
    top = reliable.nlargest(top_n, "timing_eligible_orders").sort_values("on_time_rate_pct")
    fig = go.Figure(go.Bar(
        x=top["on_time_rate_pct"], y=top["customer_state"], orientation="h", marker_color=PRIMARY,
        hovertemplate="%{y}<br>On-time: %{x:.1f}%%<br>%{customdata:,} orders<extra></extra>",
        customdata=top["timing_eligible_orders"],
    ))
    fig.update_xaxes(title="On-time delivery rate (%)")
    fig.update_yaxes(title=None)
    return _base_layout(fig, height=max(280, 26 * len(top)))
