"""
Time Intelligence

Resolves natural-language temporal expressions into concrete date-range
filters that can be injected into a QueryRequest's ``filters`` dict.

Supported expressions (case-insensitive, spaces or underscores):
  - last_quarter / last quarter
  - this_quarter / current_quarter
  - last_month / last month
  - this_month / current_month
  - ytd / year_to_date / this_year
  - last_year / previous_year
  - trailing_7_days / last_7_days
  - trailing_30_days / last_30_days
  - trailing_90_days / last_90_days
  - trailing_N_days  (any N)
"""

import re
from datetime import date, timedelta
from typing import Optional, Tuple


def _quarter_bounds(year: int, quarter: int) -> Tuple[date, date]:
    """Return (start, end) for a calendar quarter (end is exclusive)."""
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    s_month, s_day = starts[quarter]
    e_month, e_day = ends[quarter]
    return date(year, s_month, s_day), date(year, e_month, e_day)


def resolve_time_expression(
    expression: str,
    reference_date: Optional[date] = None,
) -> Optional[Tuple[date, date]]:
    """
    Parse a temporal expression and return a (start, end) date range (inclusive).

    Args:
        expression: Temporal expression string (e.g. "last quarter", "ytd")
        reference_date: The date to treat as "today". Defaults to ``date.today()``.

    Returns:
        (start_date, end_date) inclusive tuple, or None if expression is not recognised.
    """
    today = reference_date or date.today()
    expr = expression.lower().replace(" ", "_").strip()

    # --- Trailing N days ---
    trailing_match = re.match(r"(?:trailing|last)_(\d+)_days?", expr)
    if trailing_match:
        n = int(trailing_match.group(1))
        return today - timedelta(days=n - 1), today

    # --- Named expressions ---
    if expr in ("last_quarter", "previous_quarter"):
        q = (today.month - 1) // 3 + 1  # current quarter (1-4)
        prev_q = q - 1 if q > 1 else 4
        prev_y = today.year if q > 1 else today.year - 1
        return _quarter_bounds(prev_y, prev_q)

    if expr in ("this_quarter", "current_quarter"):
        q = (today.month - 1) // 3 + 1
        return _quarter_bounds(today.year, q)

    if expr in ("last_month", "previous_month"):
        first_of_this_month = today.replace(day=1)
        last_of_prev = first_of_this_month - timedelta(days=1)
        start = last_of_prev.replace(day=1)
        return start, last_of_prev

    if expr in ("this_month", "current_month"):
        start = today.replace(day=1)
        # end = last day of this month
        if today.month == 12:
            end = date(today.year, 12, 31)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)
        return start, end

    if expr in ("ytd", "year_to_date", "this_year"):
        return date(today.year, 1, 1), today

    if expr in ("last_year", "previous_year"):
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31)

    return None


def build_date_filters(
    expression: str,
    date_column: str,
    reference_date: Optional[date] = None,
) -> Optional[dict]:
    """
    Resolve a temporal expression and return filter dict entries for the
    QueryBuilder's ``filters`` field.

    The dict uses special range keys so the builder can emit BETWEEN/comparisons:
      ``{"__gte__<column>": "YYYY-MM-DD", "__lte__<column>": "YYYY-MM-DD"}``

    Args:
        expression: Temporal expression (e.g. "last_quarter")
        date_column: Column name to filter on (e.g. "date", "sale_date")
        reference_date: Reference date (defaults to today)

    Returns:
        Dict with range filter keys, or None if expression is not recognised.
    """
    result = resolve_time_expression(expression, reference_date)
    if result is None:
        return None
    start, end = result
    return {
        f"__gte__{date_column}": start.isoformat(),
        f"__lte__{date_column}": end.isoformat(),
    }


def detect_time_expression(text: str) -> Optional[str]:
    """
    Detect a temporal expression in free text.

    Returns the canonical (underscore-separated) expression string,
    or None if none is found.
    """
    patterns = [
        (r"\blast\s+quarter\b", "last_quarter"),
        (r"\bprevious\s+quarter\b", "last_quarter"),
        (r"\bthis\s+quarter\b", "this_quarter"),
        (r"\bcurrent\s+quarter\b", "this_quarter"),
        (r"\blast\s+month\b", "last_month"),
        (r"\bprevious\s+month\b", "last_month"),
        (r"\bthis\s+month\b", "this_month"),
        (r"\bcurrent\s+month\b", "this_month"),
        (r"\bq[1-4]\b", None),  # handled separately below
        (r"\bytd\b", "ytd"),
        (r"\byear[_\s]to[_\s]date\b", "ytd"),
        (r"\bthis\s+year\b", "ytd"),
        (r"\blast\s+year\b", "last_year"),
        (r"\bprevious\s+year\b", "last_year"),
        (r"\btrailing\s+(\d+)\s+days?\b", None),  # handled separately
        (r"\blast\s+(\d+)\s+days?\b", None),       # handled separately
    ]

    text_lower = text.lower()

    # Trailing/last N days
    n_days = re.search(r"\b(?:trailing|last)\s+(\d+)\s+days?\b", text_lower)
    if n_days:
        return f"trailing_{n_days.group(1)}_days"

    for pattern, canonical in patterns:
        if canonical is None:
            continue
        if re.search(pattern, text_lower):
            return canonical

    return None
