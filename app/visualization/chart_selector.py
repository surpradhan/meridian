"""
Chart Selector

Inspects query results and the QueryRequest that produced them to recommend
the most appropriate chart type. The hint is advisory — the UI layer decides
how to render it.

Chart types returned:
  "line"  — time-series data (date/month/year dimension + numeric measure)
  "bar"   — categorical dimension + numeric measure (non-time)
  "pie"   — few distinct categories + single numeric measure
  "table" — raw/multi-column results with no clear chart mapping
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Column-name patterns that indicate a date/time dimension
_DATE_PATTERNS = re.compile(
    r"\b(date|month|year|week|quarter|day|period|time|timestamp)\b",
    re.IGNORECASE,
)

# Aggregate alias prefix pattern produced by QueryBuilder (e.g. "SUM_amount")
_AGG_ALIAS_PATTERN = re.compile(r"^(SUM|COUNT|AVG|MIN|MAX)_", re.IGNORECASE)

# Maximum distinct categories for a pie chart to be sensible
_PIE_MAX_CATEGORIES = 8


def _column_names(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return []
    return list(rows[0].keys())


def _is_date_column(name: str) -> bool:
    return bool(_DATE_PATTERNS.search(name))


def _is_numeric_column(name: str, rows: List[Dict[str, Any]]) -> bool:
    """Heuristic: column is numeric if its first non-None value is int/float."""
    for row in rows:
        val = row.get(name)
        if val is not None:
            return isinstance(val, (int, float))
    return False


def _is_aggregate_column(name: str) -> bool:
    return bool(_AGG_ALIAS_PATTERN.match(name))


def select_chart_type(
    rows: List[Dict[str, Any]],
    group_by: Optional[List[str]] = None,
    aggregations: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Recommend a chart type for the given query result.

    Args:
        rows: Query result rows (list of dicts)
        group_by: GROUP BY columns from the QueryRequest
        aggregations: Aggregation dict from the QueryRequest

    Returns:
        Dict with keys:
          - ``chart_type``: "line" | "bar" | "pie" | "table"
          - ``x_axis``: suggested X-axis column name (or None)
          - ``y_axis``: suggested Y-axis column name (or None)
          - ``reason``: short human-readable explanation
    """
    if not rows:
        return {"chart_type": "table", "x_axis": None, "y_axis": None, "reason": "No data"}

    columns = _column_names(rows)
    has_aggregation = bool(aggregations) or any(_is_aggregate_column(c) for c in columns)

    if not has_aggregation:
        return {
            "chart_type": "table",
            "x_axis": None,
            "y_axis": None,
            "reason": "Raw data without aggregation — table view recommended",
        }

    # Identify dimension and measure columns
    date_cols = [c for c in columns if _is_date_column(c)]
    agg_cols = [c for c in columns if _is_aggregate_column(c) or (
        aggregations and c.split("_", 1)[-1] in aggregations
    )]

    # Fall back: any numeric non-date column is a measure candidate
    if not agg_cols:
        agg_cols = [c for c in columns if _is_numeric_column(c, rows) and not _is_date_column(c)]

    # Dimension: prefer explicit group_by, else non-numeric, non-date columns
    dim_cols = []
    if group_by:
        dim_cols = [c for c in group_by if c in columns]
    if not dim_cols:
        dim_cols = [
            c for c in columns
            if not _is_aggregate_column(c)
            and not _is_numeric_column(c, rows)
            and not _is_date_column(c)
        ]

    x_axis = None
    y_axis = agg_cols[0] if agg_cols else None

    # --- Line chart: time dimension present ---
    if date_cols and y_axis:
        x_axis = date_cols[0]
        return {
            "chart_type": "line",
            "x_axis": x_axis,
            "y_axis": y_axis,
            "reason": f"Time-series data: '{x_axis}' over '{y_axis}'",
        }

    # --- Pie chart: few categories + single measure ---
    if dim_cols and y_axis and len(rows) <= _PIE_MAX_CATEGORIES:
        x_axis = dim_cols[0]
        return {
            "chart_type": "pie",
            "x_axis": x_axis,
            "y_axis": y_axis,
            "reason": (
                f"Few categories ({len(rows)}) for '{x_axis}' — pie chart recommended"
            ),
        }

    # --- Bar chart: categorical dimension + measure ---
    if dim_cols and y_axis:
        x_axis = dim_cols[0]
        return {
            "chart_type": "bar",
            "x_axis": x_axis,
            "y_axis": y_axis,
            "reason": f"Categorical breakdown: '{x_axis}' vs '{y_axis}'",
        }

    # Default to table
    return {
        "chart_type": "table",
        "x_axis": None,
        "y_axis": None,
        "reason": "Could not determine a suitable chart type",
    }
