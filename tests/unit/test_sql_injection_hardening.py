"""
Regression tests for the SQL-identifier injection hardening.

These cover the query-builder / model controls added after the security
review: LLM-generated query plans concatenate identifiers, aggregation
functions, window arguments, and CTE bodies into SQL, so each must be
allow-listed or fail closed. Parameterization only protects *values*.
"""

import pytest
from pydantic import ValidationError

from app.views.models import QueryRequest, WindowFunction, CTEDefinition
from app.views.registry import create_test_registry
from app.query.builder import QueryBuilder


@pytest.fixture
def builder():
    return QueryBuilder(create_test_registry())


# ---------------------------------------------------------------------------
# Aggregation function allow-list (C1)
# ---------------------------------------------------------------------------

class TestAggregationAllowList:
    def test_valid_aggregation_normalized_to_upper(self):
        req = QueryRequest(selected_views=["sales_fact"], aggregations={"amount": "sum"})
        assert req.aggregations == {"amount": "SUM"}

    def test_injected_aggregation_function_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(
                selected_views=["sales_fact"],
                aggregations={"amount": "1 FROM sqlite_master--"},
            )

    def test_unknown_aggregation_function_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(selected_views=["sales_fact"], aggregations={"amount": "EVIL"})

    def test_injected_aggregation_column_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(
                selected_views=["sales_fact"],
                aggregations={"amount) FROM users--": "SUM"},
            )

    def test_valid_aggregation_builds_clean_sql(self, builder):
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["product_id"],
        )
        sql = builder.build_query(req)
        assert "SUM(sales_fact.amount) AS SUM_amount" in sql


# ---------------------------------------------------------------------------
# Column identifier resolution fails closed (C2)
# ---------------------------------------------------------------------------

class TestColumnResolutionFailsClosed:
    def test_unknown_injected_column_raises(self, builder):
        req = QueryRequest(
            selected_views=["sales_fact"],
            filters={"x) UNION SELECT account_number FROM account_dim--": "1"},
        )
        with pytest.raises(ValueError):
            builder.build_query_parameterized(req)

    def test_known_column_resolves_to_qualified_name(self, builder):
        req = QueryRequest(selected_views=["sales_fact"], filters={"amount": 100})
        sql, _ = builder.build_query_parameterized(req)
        assert "sales_fact.amount" in sql

    def test_bare_identifier_unknown_column_allowed(self, builder):
        # A bare identifier (e.g. a CTE-derived column) is permitted; only
        # identifiers carrying SQL syntax are rejected.
        assert builder._resolve_column_table("derived_total", ["sales_fact"]) == "derived_total"


# ---------------------------------------------------------------------------
# Window function arguments / alias (C3)
# ---------------------------------------------------------------------------

class TestWindowFunctionHardening:
    def test_injected_window_alias_rejected(self):
        with pytest.raises(ValidationError):
            WindowFunction(alias="x AS y FROM users--", function="ROW_NUMBER")

    def test_injected_window_arguments_rejected(self):
        with pytest.raises(ValidationError):
            WindowFunction(alias="rn", function="NTILE", arguments="4) OVER () ; DROP TABLE users--")

    def test_valid_window_arguments_allowed(self):
        wf = WindowFunction(alias="band", function="NTILE", arguments="4")
        assert wf.arguments == "4"


# ---------------------------------------------------------------------------
# CTE name / body (C3)
# ---------------------------------------------------------------------------

class TestCTEHardening:
    def test_injected_cte_name_rejected(self):
        with pytest.raises(ValidationError):
            CTEDefinition(name="x); DROP TABLE users--", sql="SELECT 1")

    def test_non_select_cte_body_rejected(self):
        with pytest.raises(ValidationError):
            CTEDefinition(name="t", sql="DELETE FROM users")

    def test_stacked_statement_cte_rejected(self):
        with pytest.raises(ValidationError):
            CTEDefinition(name="t", sql="SELECT 1; DROP TABLE users")

    def test_valid_select_cte_allowed(self):
        cte = CTEDefinition(name="top", sql="SELECT customer_id FROM sales_fact LIMIT 5")
        assert cte.name == "top"


# ---------------------------------------------------------------------------
# HAVING aggregate function allow-list (C1)
# ---------------------------------------------------------------------------

class TestHavingAllowList:
    def test_injected_having_aggregate_rejected(self, builder):
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["product_id"],
            having={"EVIL_amount": {"op": ">", "value": 10}},
        )
        with pytest.raises(ValueError):
            builder.build_query_parameterized(req)

    def test_valid_having_builds(self, builder):
        req = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["product_id"],
            having={"SUM_amount": {"op": ">", "value": 10}},
        )
        sql, params = builder.build_query_parameterized(req)
        assert "HAVING SUM(sales_fact.amount) > ?" in sql
        assert params == [10]
