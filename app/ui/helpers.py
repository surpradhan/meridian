"""
Pure UI helper functions — zero Gradio dependency.

Extracted so they can be unit-tested without importing the Gradio runtime
(which has a transitive dependency on huggingface_hub that can break in CI
when package versions are mismatched).

gradio_app.py imports these and wraps the dict-returning helpers with
gr.update() where Gradio's event system requires it.
"""

from typing import Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Height used for both real charts and the empty-state placeholder; keeping
# them identical prevents layout shift when switching between tab states.
CHART_HEIGHT = 300

# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def build_empty_chart(message: str = "No data to visualise") -> go.Figure:
    """Return a styled empty Plotly figure with a centred annotation.

    Height matches CHART_HEIGHT (same as real charts) to prevent layout
    shift when toggling between populated and empty Chart tab states.
    """
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=15, color="#64748b", family="Inter, system-ui, sans-serif"),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.3)",
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        margin=dict(l=40, r=40, t=40, b=40),
        height=CHART_HEIGHT,
    )
    return fig


def build_plotly_figure(rows: list, viz: dict) -> Optional[go.Figure]:
    """Convert a chart hint + result rows into a Plotly figure.

    Returns None when the data or hint is unsuitable for charting (table
    type, missing columns, empty rows, or unsupported chart_type).
    """
    if not rows or not viz or viz.get("chart_type") == "table":
        return None
    df = pd.DataFrame(rows)
    chart_type = viz.get("chart_type")
    x = viz.get("x_axis")
    y = viz.get("y_axis")
    title = viz.get("reason", "")
    if not x or not y or x not in df.columns or y not in df.columns:
        return None
    try:
        layout_opts = dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15,23,42,0.5)",
            font=dict(family="Inter, system-ui, sans-serif", color="#94a3b8"),
            title_font=dict(color="#e2e8f0", size=14),
            xaxis=dict(gridcolor="rgba(51,65,85,0.5)", zerolinecolor="#334155"),
            yaxis=dict(gridcolor="rgba(51,65,85,0.5)", zerolinecolor="#334155"),
            margin=dict(l=40, r=20, t=40, b=40),
            height=CHART_HEIGHT,
        )
        color_seq = ["#0d9488", "#f59e0b", "#6366f1", "#10b981", "#ef4444", "#8b5cf6"]
        if chart_type == "line":
            fig = px.line(df, x=x, y=y, title=title, color_discrete_sequence=color_seq)
        elif chart_type == "bar":
            fig = px.bar(df, x=x, y=y, title=title, color_discrete_sequence=color_seq)
        elif chart_type == "pie":
            fig = px.pie(df, names=x, values=y, title=title, color_discrete_sequence=color_seq)
        else:
            return None
        fig.update_layout(**layout_opts)
        return fig
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Button-state helpers
#
# These return plain dicts that are compatible with Gradio's gr.update()
# wire format.  gradio_app.py passes these dicts straight through — Gradio
# accepts plain dicts wherever gr.update() is expected.
# ---------------------------------------------------------------------------

def thinking_label_dict(explain_on: bool) -> dict:
    """Return a submit-button update dict for the loading state.

    Label is context-aware: "Analysing…" when Explain mode is active
    (signals the extra LLM step), otherwise the generic "Thinking…".
    """
    label = "Analysing\u2026" if explain_on else "Thinking\u2026"
    return {"value": label, "interactive": False, "__type__": "update"}


def pick_suggestion(idx: int, sugg: list, explain_on: bool = False) -> tuple:
    """Populate the question box from the suggestion list by index."""
    text = sugg[idx] if idx < len(sugg) else ""
    return text, thinking_label_dict(explain_on)
