"""
Unit tests for MERIDIAN Gradio UI helper functions.

Imports from app.ui.helpers (not gradio_app) so the test module never
touches the Gradio runtime.  This avoids the transitive huggingface_hub
dependency that can break CI when package versions are mismatched.
"""

import pytest
import plotly.graph_objects as go

from app.ui.helpers import (
    CHART_HEIGHT,
    build_empty_chart,
    build_plotly_figure,
    thinking_label_dict,
    pick_suggestion,
)


# ---------------------------------------------------------------------------
# build_empty_chart
# ---------------------------------------------------------------------------

class TestBuildEmptyChart:

    def test_returns_go_figure(self):
        fig = build_empty_chart()
        assert isinstance(fig, go.Figure)

    def test_default_annotation_text(self):
        fig = build_empty_chart()
        annotations = fig.layout.annotations
        assert len(annotations) == 1
        assert annotations[0].text == "No data to visualise"

    def test_custom_message(self):
        msg = "Results are best viewed in the Table tab"
        fig = build_empty_chart(msg)
        assert fig.layout.annotations[0].text == msg

    def test_height_matches_shared_constant(self):
        fig = build_empty_chart()
        assert fig.layout.height == CHART_HEIGHT

    def test_transparent_background(self):
        fig = build_empty_chart()
        assert "rgba(0,0,0,0)" in fig.layout.paper_bgcolor

    def test_axes_hidden(self):
        fig = build_empty_chart()
        assert fig.layout.xaxis.showticklabels is False
        assert fig.layout.yaxis.showticklabels is False


# ---------------------------------------------------------------------------
# build_plotly_figure — height consistency
# ---------------------------------------------------------------------------

class TestBuildPlotlyFigureHeight:
    """Real chart height must equal empty-chart height to avoid layout shift."""

    def test_bar_chart_height_matches_constant(self):
        rows = [{"cat": "A", "val": 10}, {"cat": "B", "val": 20}]
        viz = {"chart_type": "bar", "x_axis": "cat", "y_axis": "val", "reason": "test"}
        fig = build_plotly_figure(rows, viz)
        assert fig is not None
        assert fig.layout.height == CHART_HEIGHT

    def test_line_chart_height_matches_constant(self):
        rows = [{"x": 1, "y": 5}, {"x": 2, "y": 8}]
        viz = {"chart_type": "line", "x_axis": "x", "y_axis": "y", "reason": ""}
        fig = build_plotly_figure(rows, viz)
        assert fig is not None
        assert fig.layout.height == CHART_HEIGHT

    def test_returns_none_for_missing_columns(self):
        rows = [{"a": 1}]
        viz = {"chart_type": "bar", "x_axis": "missing_x", "y_axis": "missing_y"}
        assert build_plotly_figure(rows, viz) is None

    def test_returns_none_for_empty_rows(self):
        assert build_plotly_figure([], {"chart_type": "bar"}) is None

    def test_returns_none_for_table_type(self):
        rows = [{"a": 1}]
        assert build_plotly_figure(rows, {"chart_type": "table"}) is None


# ---------------------------------------------------------------------------
# thinking_label_dict
# ---------------------------------------------------------------------------

class TestThinkingLabelDict:

    def test_explain_off_says_thinking(self):
        result = thinking_label_dict(False)
        assert result["value"] == "Thinking\u2026"
        assert result["interactive"] is False

    def test_explain_on_says_analysing(self):
        result = thinking_label_dict(True)
        assert result["value"] == "Analysing\u2026"
        assert result["interactive"] is False

    def test_returns_dict(self):
        assert isinstance(thinking_label_dict(False), dict)


# ---------------------------------------------------------------------------
# pick_suggestion
# ---------------------------------------------------------------------------

class TestPickSuggestion:

    def test_returns_text_at_index(self):
        sugg = ["Q1", "Q2", "Q3"]
        text, btn = pick_suggestion(1, sugg, explain_on=False)
        assert text == "Q2"

    def test_explain_off_label(self):
        text, btn = pick_suggestion(0, ["Q"], explain_on=False)
        assert btn["value"] == "Thinking\u2026"

    def test_explain_on_label(self):
        text, btn = pick_suggestion(0, ["Q"], explain_on=True)
        assert btn["value"] == "Analysing\u2026"

    def test_out_of_range_index_returns_empty(self):
        text, _ = pick_suggestion(5, ["only one"], explain_on=False)
        assert text == ""
