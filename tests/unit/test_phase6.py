"""
Unit Tests for Phase 6: Advanced Query Capabilities

Covers:
- Multi-hop join pathfinding (ViewRegistry.find_join_path)
- Time intelligence (resolve_time_expression, detect_time_expression, build_date_filters)
- QueryBuilder: HAVING, ORDER BY, CTEs, window functions, time-expression resolution
- QueryBuilder: multi-hop FROM clause injection
- Visualization hint (chart_selector.select_chart_type)
"""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.views.models import (
    ColumnSchema,
    ViewSchema,
    JoinRelationship,
    QueryRequest,
    WindowFunction,
    CTEDefinition,
)
from app.views.registry import ViewRegistry
from app.query.builder import QueryBuilder
from app.query.time_intelligence import (
    resolve_time_expression,
    detect_time_expression,
    build_date_filters,
)
from app.visualization.chart_selector import select_chart_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col(name: str, dtype: str = "VARCHAR") -> ColumnSchema:
    return ColumnSchema(name=name, data_type=dtype)


def _make_view(name: str, domain: str, cols: list) -> ViewSchema:
    return ViewSchema(name=name, view_type="fact", domain=domain, columns=cols)


def _make_join(src: str, tgt: str, src_col: str, tgt_col: str) -> JoinRelationship:
    return JoinRelationship(
        source_view=src,
        target_view=tgt,
        source_columns=[src_col],
        target_columns=[tgt_col],
        relationship_type="many_to_one",
        description=f"{src} → {tgt}",
    )


def _minimal_registry() -> ViewRegistry:
    """Registry with three views in a chain: A → B → C (no direct A-C join)."""
    reg = ViewRegistry()
    reg.register_view(_make_view("view_a", "test", [_make_col("a_id"), _make_col("b_ref")]))
    reg.register_view(_make_view("view_b", "test", [_make_col("b_id"), _make_col("c_ref"), _make_col("b_ref")]))
    reg.register_view(_make_view("view_c", "test", [_make_col("c_id"), _make_col("c_ref")]))
    reg.register_join(_make_join("view_a", "view_b", "b_ref", "b_id"))
    reg.register_join(_make_join("view_b", "view_c", "c_ref", "c_id"))
    return reg


# ---------------------------------------------------------------------------
# Multi-hop join pathfinding
# ---------------------------------------------------------------------------

class TestFindJoinPath:

    def test_direct_path(self):
        reg = _minimal_registry()
        path = reg.find_join_path("view_a", "view_b")
        assert path == ["view_a", "view_b"]

    def test_two_hop_path(self):
        reg = _minimal_registry()
        path = reg.find_join_path("view_a", "view_c")
        assert path == ["view_a", "view_b", "view_c"]

    def test_reverse_direction(self):
        """Should also find path when traversing joins in reverse."""
        reg = _minimal_registry()
        path = reg.find_join_path("view_c", "view_a")
        assert path is not None
        assert path[0] == "view_c"
        assert path[-1] == "view_a"

    def test_same_view(self):
        reg = _minimal_registry()
        path = reg.find_join_path("view_a", "view_a")
        assert path == ["view_a"]

    def test_unreachable_view(self):
        reg = _minimal_registry()
        reg.register_view(_make_view("isolated", "test", [_make_col("x")]))
        path = reg.find_join_path("view_a", "isolated")
        assert path is None

    def test_unknown_view_returns_none(self):
        reg = _minimal_registry()
        assert reg.find_join_path("view_a", "does_not_exist") is None
        assert reg.find_join_path("does_not_exist", "view_a") is None


# ---------------------------------------------------------------------------
# Time Intelligence
# ---------------------------------------------------------------------------

REF = date(2026, 4, 9)  # today in this session


class TestResolveTimeExpression:

    def test_last_quarter(self):
        start, end = resolve_time_expression("last_quarter", REF)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_this_quarter(self):
        start, end = resolve_time_expression("this_quarter", REF)
        assert start == date(2026, 4, 1)
        assert end == date(2026, 6, 30)

    def test_last_month(self):
        start, end = resolve_time_expression("last_month", REF)
        assert start == date(2026, 3, 1)
        assert end == date(2026, 3, 31)

    def test_this_month(self):
        start, end = resolve_time_expression("this_month", REF)
        assert start == date(2026, 4, 1)
        assert end == date(2026, 4, 30)

    def test_ytd(self):
        start, end = resolve_time_expression("ytd", REF)
        assert start == date(2026, 1, 1)
        assert end == REF

    def test_last_year(self):
        start, end = resolve_time_expression("last_year", REF)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 12, 31)

    def test_trailing_30_days(self):
        start, end = resolve_time_expression("trailing_30_days", REF)
        assert end == REF
        assert start == REF - timedelta(days=29)

    def test_trailing_7_days(self):
        start, end = resolve_time_expression("trailing_7_days", REF)
        assert end == REF
        assert (end - start).days == 6

    def test_unknown_expression_returns_none(self):
        assert resolve_time_expression("something_weird", REF) is None

    def test_alternative_spellings(self):
        assert resolve_time_expression("previous_quarter", REF) == \
               resolve_time_expression("last_quarter", REF)
        assert resolve_time_expression("year_to_date", REF) == \
               resolve_time_expression("ytd", REF)

    def test_q1_boundary(self):
        """last_quarter from Q1 should return previous year Q4."""
        jan_ref = date(2026, 2, 15)
        start, end = resolve_time_expression("last_quarter", jan_ref)
        assert start == date(2025, 10, 1)
        assert end == date(2025, 12, 31)


class TestDetectTimeExpression:

    def test_detects_last_quarter(self):
        assert detect_time_expression("show me revenue for last quarter") == "last_quarter"

    def test_detects_ytd(self):
        assert detect_time_expression("YTD sales by region") == "ytd"

    def test_detects_trailing_n(self):
        assert detect_time_expression("orders in the trailing 14 days") == "trailing_14_days"

    def test_no_temporal_expression(self):
        assert detect_time_expression("total sales by customer") is None


class TestBuildDateFilters:

    def test_produces_gte_lte_keys(self):
        filters = build_date_filters("last_quarter", "date", REF)
        assert filters is not None
        assert "__gte__date" in filters
        assert "__lte__date" in filters
        assert filters["__gte__date"] == "2026-01-01"
        assert filters["__lte__date"] == "2026-03-31"

    def test_unknown_expression_returns_none(self):
        assert build_date_filters("not_a_real_expression", "date", REF) is None


# ---------------------------------------------------------------------------
# QueryBuilder: advanced SQL
# ---------------------------------------------------------------------------

def _sales_registry() -> ViewRegistry:
    """Minimal sales registry with sales_fact + customer_dim."""
    reg = ViewRegistry()
    reg.register_view(_make_view("sales_fact", "sales", [
        _make_col("sale_id", "INT"),
        _make_col("customer_id", "INT"),
        _make_col("amount", "DECIMAL"),
        _make_col("date", "DATE"),
        _make_col("region", "VARCHAR"),
    ]))
    reg.register_view(_make_view("customer_dim", "sales", [
        _make_col("customer_id", "INT"),
        _make_col("name", "VARCHAR"),
        _make_col("segment", "VARCHAR"),
    ]))
    reg.register_join(_make_join("sales_fact", "customer_dim", "customer_id", "customer_id"))
    return reg


class TestQueryBuilderHaving:

    def test_having_clause_generated(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["region"],
            having={"SUM_amount": {"op": ">", "value": 5000}},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "HAVING" in sql
        assert "SUM(sales_fact.amount) > ?" in sql
        assert 5000 in params

    def test_no_having_without_aggregations(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            having={"SUM_amount": {"op": ">", "value": 5000}},
        )
        sql = builder.build_query(req)
        assert "HAVING" not in sql


class TestQueryBuilderOrderBy:

    def test_order_by_aggregate_alias(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["region"],
            order_by=[{"column": "SUM_amount", "direction": "DESC"}],
        )
        sql = builder.build_query(req)
        assert "ORDER BY SUM_amount DESC" in sql

    def test_order_by_plain_column(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            order_by=[{"column": "date", "direction": "ASC"}],
        )
        sql = builder.build_query(req)
        assert "ORDER BY sales_fact.date ASC" in sql


class TestQueryBuilderCTE:

    def test_cte_prepended(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            ctes=[CTEDefinition(name="high_value", sql="SELECT sale_id FROM sales_fact WHERE amount > 1000")],
        )
        sql = builder.build_query(req)
        assert sql.startswith("WITH high_value AS (")

    def test_multiple_ctes(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            ctes=[
                CTEDefinition(name="cte_a", sql="SELECT 1"),
                CTEDefinition(name="cte_b", sql="SELECT 2"),
            ],
        )
        sql = builder.build_query(req)
        assert "cte_a AS (" in sql
        assert "cte_b AS (" in sql


class TestQueryBuilderWindowFunctions:

    def test_window_function_in_select(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            window_functions=[
                WindowFunction(
                    alias="rank",
                    function="ROW_NUMBER",
                    partition_by=["region"],
                    order_by=[{"column": "amount", "direction": "DESC"}],
                )
            ],
        )
        sql = builder.build_query(req)
        assert "ROW_NUMBER() OVER" in sql
        assert "PARTITION BY sales_fact.region" in sql
        assert "ORDER BY sales_fact.amount DESC" in sql
        assert "AS rank" in sql

    def test_window_without_partition(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            window_functions=[
                WindowFunction(
                    alias="overall_rank",
                    function="RANK",
                    order_by=[{"column": "amount", "direction": "ASC"}],
                )
            ],
        )
        sql = builder.build_query(req)
        assert "RANK() OVER" in sql
        assert "PARTITION BY" not in sql


class TestQueryBuilderTimeExpression:

    def test_time_expression_becomes_where_filter(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            time_expression="last_quarter",
            time_column="date",
        )
        with patch("app.query.time_intelligence.date") as mock_date:
            mock_date.today.return_value = REF
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            sql, params = builder.build_query_parameterized(req)

        assert "WHERE" in sql
        assert "?" in sql
        assert "2026-01-01" in params
        assert "2026-03-31" in params
        assert "time_expression" not in sql.lower()

    def test_missing_time_column_skips_filter(self):
        """time_expression without time_column should not crash — just skip."""
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            time_expression="last_quarter",
            # time_column intentionally omitted
        )
        sql = builder.build_query(req)
        # No crash, no spurious WHERE
        assert "sales_fact" in sql


class TestQueryBuilderMultiHop:

    def test_multihop_from_clause(self):
        """Query on view_a and view_c should auto-inject view_b in the FROM clause."""
        reg = _minimal_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(selected_views=["view_a", "view_c"])
        sql = builder.build_query(req)
        from_clause = sql[sql.index("FROM"):]
        assert "view_a" in from_clause
        assert "view_b" in from_clause
        assert "view_c" in from_clause
        # The JOIN for view_b must precede the JOIN for view_c in the FROM clause
        assert from_clause.index("view_b") < from_clause.index("view_c")

    def test_direct_join_not_duplicated(self):
        """Direct join should not inject extra intermediate views."""
        reg = _minimal_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(selected_views=["view_a", "view_b"])
        sql = builder.build_query(req)
        # view_b appears in SELECT (view_b.*), JOIN keyword, and ON clause — no extra JOIN
        assert "INNER JOIN view_b" in sql
        assert sql.count("INNER JOIN view_b") == 1
        assert "view_c" not in sql

    def test_no_path_raises(self):
        reg = _minimal_registry()
        reg.register_view(_make_view("orphan", "test", [_make_col("x")]))
        builder = QueryBuilder(reg)
        req = QueryRequest(selected_views=["view_a", "orphan"])
        with pytest.raises(ValueError, match="No join path"):
            builder.build_query(req)


# ---------------------------------------------------------------------------
# Visualization hint
# ---------------------------------------------------------------------------

class TestSelectChartType:

    def _agg_rows(self, dim_col: str, measure_col: str, n: int = 5):
        return [{dim_col: f"cat_{i}", measure_col: i * 100} for i in range(n)]

    def test_bar_chart_for_categorical(self):
        # Use more rows than _PIE_MAX_CATEGORIES (8) to get a bar chart
        rows = self._agg_rows("region", "SUM_amount", n=10)
        hint = select_chart_type(rows, group_by=["region"], aggregations={"amount": "SUM"})
        assert hint["chart_type"] == "bar"
        assert hint["x_axis"] == "region"
        assert hint["y_axis"] == "SUM_amount"

    def test_line_chart_for_time_series(self):
        rows = [{"date": f"2026-0{i+1}-01", "SUM_amount": i * 500} for i in range(6)]
        hint = select_chart_type(rows, group_by=["date"], aggregations={"amount": "SUM"})
        assert hint["chart_type"] == "line"
        assert hint["x_axis"] == "date"

    def test_pie_chart_for_few_categories(self):
        rows = self._agg_rows("segment", "SUM_amount", n=4)
        hint = select_chart_type(rows, group_by=["segment"], aggregations={"amount": "SUM"})
        assert hint["chart_type"] == "pie"

    def test_table_for_no_aggregation(self):
        rows = [{"sale_id": 1, "amount": 100}, {"sale_id": 2, "amount": 200}]
        hint = select_chart_type(rows)
        assert hint["chart_type"] == "table"

    def test_table_for_empty_rows(self):
        hint = select_chart_type([])
        assert hint["chart_type"] == "table"

    def test_bar_chart_for_many_categories(self):
        """More than _PIE_MAX_CATEGORIES rows should use bar not pie."""
        rows = self._agg_rows("region", "SUM_amount", n=10)
        hint = select_chart_type(rows, group_by=["region"], aggregations={"amount": "SUM"})
        assert hint["chart_type"] == "bar"


# ---------------------------------------------------------------------------
# Issue fixes — regression tests
# ---------------------------------------------------------------------------

class TestWindowFunctionValidation:
    """Issue 1 — WindowFunction.function must be a known SQL window function."""

    def test_valid_functions_accepted(self):
        for fn in ["ROW_NUMBER", "RANK", "DENSE_RANK", "SUM", "AVG", "COUNT", "MIN", "MAX"]:
            wf = WindowFunction(alias="x", function=fn)
            assert wf.function == fn

    def test_lowercase_normalised_to_upper(self):
        wf = WindowFunction(alias="x", function="row_number")
        assert wf.function == "ROW_NUMBER"

    def test_invalid_function_raises(self):
        with pytest.raises(Exception, match="Invalid window function"):
            WindowFunction(alias="x", function="FOOBAR")

    def test_sql_injection_in_function_raises(self):
        with pytest.raises(Exception, match="Invalid window function"):
            WindowFunction(alias="x", function="ROW_NUMBER(); DROP TABLE--")


class TestOrderByItemModel:
    """Issue 3 — OrderByItem enforces 'column' and 'direction' types."""

    def test_order_by_item_requires_column(self):
        from app.views.models import OrderByItem
        with pytest.raises(Exception):
            OrderByItem(direction="DESC")  # column is required

    def test_order_by_item_direction_must_be_asc_or_desc(self):
        from app.views.models import OrderByItem
        with pytest.raises(Exception):
            OrderByItem(column="amount", direction="SIDEWAYS")

    def test_order_by_item_defaults_asc(self):
        from app.views.models import OrderByItem
        item = OrderByItem(column="amount")
        assert item.direction == "ASC"

    def test_window_function_order_by_uses_typed_items(self):
        """WindowFunction.order_by items are OrderByItem, not raw dicts."""
        wf = WindowFunction(
            alias="r",
            function="ROW_NUMBER",
            order_by=[{"column": "amount", "direction": "DESC"}],
        )
        assert wf.order_by[0].column == "amount"
        assert wf.order_by[0].direction == "DESC"

    def test_window_order_by_missing_column_raises(self):
        """Missing 'column' key in order_by dict must fail at model construction."""
        with pytest.raises(Exception):
            WindowFunction(
                alias="r",
                function="RANK",
                order_by=[{"direction": "DESC"}],  # column missing
            )


class TestTimeColumnValidation:
    """Issue 2 — time_column must exist in a selected view."""

    def test_valid_time_column_passes(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            time_expression="last_quarter",
            time_column="date",
        )
        with patch("app.query.time_intelligence.date") as mock_date:
            mock_date.today.return_value = REF
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            sql, params = builder.build_query_parameterized(req)
        assert "2026-01-01" in params
        assert "WHERE" in sql

    def test_invalid_time_column_raises(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            time_expression="last_quarter",
            time_column="nonexistent_col",
        )
        with pytest.raises(ValueError, match="time_column 'nonexistent_col' not found"):
            builder.build_query(req)


class TestHavingValidation:
    """Issues 4 & 5 — HAVING rejects non-numeric values and bad operators."""

    def test_having_numeric_value_accepted(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["sale_id"],
            having={"SUM_amount": {"op": ">", "value": 5000}},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "HAVING" in sql
        assert 5000 in params

    def test_having_string_value_raises(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["sale_id"],
            having={"SUM_amount": {"op": ">", "value": "'; DROP TABLE--"}},
        )
        with pytest.raises(ValueError, match="must be numeric"):
            builder.build_query(req)

    def test_having_disallowed_operator_raises(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["sale_id"],
            having={"SUM_amount": {"op": "LIKE", "value": 100}},
        )
        with pytest.raises(ValueError, match="not allowed"):
            builder.build_query(req)


class TestParameterizedQuery:
    """Issue 5 — WHERE/HAVING values bound as parameters, not inlined."""

    def test_string_filter_uses_placeholder(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            filters={"region": "O'Brien"},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "?" in sql
        assert "O'Brien" not in sql  # must NOT be inlined
        assert params == ["O'Brien"]

    def test_numeric_filter_uses_placeholder(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            filters={"sale_id": 42},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "?" in sql
        assert "42" not in sql
        assert params == [42]

    def test_date_range_filters_use_placeholders(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            time_expression="last_quarter",
            time_column="date",
        )
        with patch("app.query.time_intelligence.date") as mock_date:
            mock_date.today.return_value = REF
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            sql, params = builder.build_query_parameterized(req)
        assert sql.count("?") == 2
        assert "2026-01-01" in params
        assert "2026-03-31" in params
        assert "2026-01-01" not in sql

    def test_having_numeric_uses_placeholder(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["sale_id"],
            having={"SUM_amount": {"op": ">", "value": 9999}},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "HAVING" in sql
        assert "?" in sql
        assert 9999 in params
        assert "9999" not in sql

    def test_null_filter_has_no_placeholder(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            filters={"sale_id": None},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "IS NULL" in sql
        assert params == []

    def test_no_filters_returns_empty_params(self):
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(selected_views=["sales_fact"])
        sql, params = builder.build_query_parameterized(req)
        assert params == []

    def test_build_query_string_delegates_to_parameterized(self):
        """build_query() SQL must use ? placeholders, not inlined values."""
        reg = _sales_registry()
        builder = QueryBuilder(reg)
        req = QueryRequest(
            selected_views=["sales_fact"],
            filters={"region": "O'Brien"},
        )
        sql = builder.build_query(req)
        # Values must be placeholders, never inlined in the template
        assert "?" in sql
        assert "O'Brien" not in sql


class TestTimeIntelligenceDefaultDate:
    """Issue 7 — resolve_time_expression without reference_date uses today."""

    def test_default_reference_date_uses_today(self):
        """With no reference_date, the function should call date.today()."""
        fake_today = date(2025, 7, 15)
        with patch("app.query.time_intelligence.date") as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            start, end = resolve_time_expression("last_month")
        assert start == date(2025, 6, 1)
        assert end == date(2025, 6, 30)

    def test_explicit_reference_date_overrides_today(self):
        """Explicit reference_date must take precedence over today."""
        start, end = resolve_time_expression("last_month", reference_date=date(2025, 3, 10))
        assert start == date(2025, 2, 1)
        assert end == date(2025, 2, 28)
