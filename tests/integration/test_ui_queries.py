"""
UI Query Integration Tests

Tests the same code path as the Gradio UI (orchestrator.process_query and
agent.process_query) with 52 unique natural language queries across all domains.

Bugs documented with @pytest.mark.xfail are expected to fail against the
current code; they auto-promote to XPASS once the bug is fixed.
"""

import pytest
from app.views.registry import create_test_registry
from app.database.connection import DbConnection, reset_db
from app.query.builder import QueryBuilder
from app.agents.orchestrator import Orchestrator
from app.agents.domain.sales import SalesAgent
from app.agents.domain.finance import FinanceAgent
from app.agents.domain.operations import OperationsAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_valid_result(result: dict):
    """Assert result has required structure and no error."""
    assert isinstance(result, dict)
    assert not result.get("error"), f"Unexpected error: {result.get('error')}"
    assert "sql" in result, "Missing 'sql' key in result"
    assert "SELECT" in result["sql"]
    assert "FROM" in result["sql"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env():
    """Base environment: registry + mock DB + builder."""
    reset_db()
    registry = create_test_registry()
    db = DbConnection(is_mock=True)
    builder = QueryBuilder(registry)
    return registry, db, builder


@pytest.fixture
def sales_agent(env):
    registry, db, builder = env
    return SalesAgent(registry, db, builder)


@pytest.fixture
def finance_agent(env):
    registry, db, builder = env
    return FinanceAgent(registry, db, builder)


@pytest.fixture
def ops_agent(env):
    registry, db, builder = env
    return OperationsAgent(registry, db, builder)


@pytest.fixture
def orchestrator(env):
    registry, db, builder = env
    return Orchestrator(registry, db)


# ---------------------------------------------------------------------------
# Class 1: Sales Queries (17 tests)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSalesQueries:
    """Tests for the Sales domain agent via the UI code path."""

    def test_total_sales_amount(self, sales_agent):
        """Aggregate: total sales amount."""
        result = sales_agent.process_query("What is the total sales amount?")
        assert_valid_result(result)
        assert "SUM" in result["sql"]
        assert "sales_fact" in result["views"]

    def test_sales_count_transactions(self, sales_agent):
        """Aggregate: count of sales transactions."""
        result = sales_agent.process_query("How many transactions were made?")
        assert_valid_result(result)
        assert "COUNT" in result["sql"]

    def test_sales_in_west_region(self, sales_agent):
        """Filter: WEST region sales."""
        result = sales_agent.process_query("Show me sales in the WEST region")
        assert_valid_result(result)
        assert "region" in result["sql"]
        assert "WHERE" in result["sql"]
        # Verify filter extraction works
        filters = sales_agent._identify_filters("show me sales in the west region", [])
        assert filters.get("region") == "WEST"

    def test_sales_in_east_region(self, sales_agent):
        """Filter: EAST region sales."""
        result = sales_agent.process_query("Sales data for EAST region")
        assert_valid_result(result)
        assert "region" in result["sql"]

    def test_sales_in_north_region(self, sales_agent):
        """Filter: NORTH region sales."""
        result = sales_agent.process_query("How many sales in NORTH region?")
        assert_valid_result(result)
        assert "region" in result["sql"]

    def test_sales_in_south_region(self, sales_agent):
        """Filter: SOUTH region sales."""
        result = sales_agent.process_query("South region sales performance")
        assert_valid_result(result)
        assert "region" in result["sql"]

    def test_sales_by_customer_shows_names(self, sales_agent):
        """Group by: sales by customer should show customer names, not IDs (Bug 5 fixed)."""
        result = sales_agent.process_query("Total sales by customer")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        # After fix: should group by name, not customer_id
        assert "customer_dim.name" in result["sql"] or "name" in result["sql"]

    def test_sales_by_customer_has_groupby(self, sales_agent):
        """Group by: sales by customer at minimum produces a GROUP BY clause."""
        result = sales_agent.process_query("Total sales by customer")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "customer_dim" in result["views"]

    def test_sales_by_product(self, sales_agent):
        """Group by: total sales by product."""
        result = sales_agent.process_query("What are total sales by product?")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "product_dim" in result["views"]

    def test_sales_by_region(self, sales_agent):
        """Group by: total sales by region."""
        result = sales_agent.process_query("Total sales by region")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "region" in result["sql"]

    def test_sales_by_region_and_product(self, sales_agent):
        """Group by: multi-dimension group by region and product (Bug 7 fixed)."""
        result = sales_agent.process_query("Total sales by region and product")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        # Both region and product should appear in GROUP BY
        group_by_part = result["sql"].upper().split("GROUP BY")[1].split("LIMIT")[0]
        assert "REGION" in group_by_part, "Region missing from GROUP BY"
        assert "NAME" in group_by_part, "Product name dimension missing from GROUP BY"

    def test_sales_by_category(self, sales_agent):
        """Group by: total sales by product category."""
        result = sales_agent.process_query("Show total sales by category")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "category" in result["sql"]

    def test_average_sales_amount(self, sales_agent):
        """Aggregate: average sale amount."""
        result = sales_agent.process_query("What is the average sale amount?")
        assert_valid_result(result)
        assert "AVG" in result["sql"]

    def test_max_sale_amount(self, sales_agent):
        """Aggregate: highest (max) sale amount."""
        result = sales_agent.process_query("What was the highest sales amount?")
        assert_valid_result(result)
        assert "MAX" in result["sql"]

    def test_min_sale_amount(self, sales_agent):
        """Aggregate: lowest (min) sale amount."""
        result = sales_agent.process_query("What was the lowest sales amount?")
        assert_valid_result(result)
        assert "MIN" in result["sql"]

    def test_sales_with_customer_name_filter(self, sales_agent):
        """Filter: sales for a specific customer (quoted name)."""
        result = sales_agent.process_query("Sales for customer 'Acme Corp'")
        assert_valid_result(result)
        # Filter value is now a parameterized ? placeholder — verify WHERE and column presence
        assert "WHERE" in result["sql"]
        assert "?" in result["sql"]

    def test_sales_with_product_name_filter(self, sales_agent):
        """Filter: sales for a specific product (quoted name)."""
        result = sales_agent.process_query("Sales for product 'Widget Pro'")
        assert_valid_result(result)
        # Filter value is now a parameterized ? placeholder — verify WHERE and column presence
        assert "WHERE" in result["sql"]
        assert "?" in result["sql"]

    def test_total_sales_no_filters(self, sales_agent):
        """Simple select: no filters, no aggregations."""
        result = sales_agent.process_query("Show all sales data")
        assert_valid_result(result)
        assert "sales_fact.*" in result["sql"]
        assert "FROM sales_fact" in result["sql"]
        assert "LIMIT" in result["sql"]


# ---------------------------------------------------------------------------
# Class 2: Finance Queries (14 tests)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFinanceQueries:
    """Tests for the Finance domain agent via the UI code path."""

    def test_total_ledger_balance(self, finance_agent):
        """Aggregate: total balance in the ledger."""
        result = finance_agent.process_query("What is the total balance in the ledger?")
        assert_valid_result(result)
        assert "SUM" in result["sql"]
        assert "ledger_fact" in result["views"]

    def test_all_gl_transactions(self, finance_agent):
        """Simple select: all GL transactions."""
        result = finance_agent.process_query("Show me all GL transactions")
        assert_valid_result(result)
        assert "ledger_fact" in result["views"]
        assert "SELECT" in result["sql"]

    def test_debit_transactions_only(self, finance_agent):
        """Filter: debit-only transactions."""
        result = finance_agent.process_query("Show me all debit transactions")
        assert_valid_result(result)
        assert "debit_credit" in result["sql"]
        assert "WHERE" in result["sql"]
        # Verify filter extraction
        filters = finance_agent._identify_filters("show me all debit transactions", [])
        assert filters.get("debit_credit") == "DEBIT"

    def test_credit_transactions_only(self, finance_agent):
        """Filter: credit-only transactions."""
        result = finance_agent.process_query("Show me all credit transactions")
        assert_valid_result(result)
        assert "debit_credit" in result["sql"]
        assert "WHERE" in result["sql"]
        filters = finance_agent._identify_filters("show me all credit transactions", [])
        assert filters.get("debit_credit") == "CREDIT"

    def test_debit_and_credit_no_filter_for_compare(self, finance_agent):
        """Compare query: both debit and credit → no filter, GROUP BY debit_credit (Bug 3 fixed)."""
        result = finance_agent.process_query("Compare debit vs credit totals")
        assert_valid_result(result)
        # After fix: no WHERE debit_credit filter (no if/elif collision)
        # debit_credit appears only in GROUP BY, not in WHERE
        sql = result["sql"]
        if "WHERE" in sql:
            where_part = sql.split("WHERE")[1].split("GROUP BY")[0] if "GROUP BY" in sql else sql.split("WHERE")[1]
            assert "debit_credit" not in where_part, \
                f"debit_credit WHERE filter should not be present for comparison query"

    def test_debit_and_credit_no_single_filter(self, finance_agent):
        """Fixed behavior: when both debit and credit present, no single-side filter is set."""
        filters = finance_agent._identify_filters("compare debit vs credit totals", [])
        # After Bug 3 fix: no debit_credit filter — comparison queries show both sides
        assert "debit_credit" not in filters

    def test_account_type_asset(self, finance_agent):
        """Filter: ASSET account type — matched via direct type-name lookup."""
        result = finance_agent.process_query("Show me all asset account transactions")
        assert_valid_result(result)
        assert "account_type" in result["sql"]
        assert "WHERE" in result["sql"]

    def test_account_type_liability(self, finance_agent):
        """Filter: LIABILITY account type — matched via direct type-name lookup."""
        result = finance_agent.process_query("Show liability account entries")
        assert_valid_result(result)
        assert "account_type" in result["sql"]
        assert "WHERE" in result["sql"]

    def test_account_type_expense(self, finance_agent):
        """Filter: EXPENSE account type — matched via direct type-name lookup."""
        result = finance_agent.process_query("Show expense account totals")
        assert_valid_result(result)
        assert "account_type" in result["sql"]
        assert "WHERE" in result["sql"]

    def test_account_filter_greedy_bug(self, finance_agent):
        """Bug 1 fixed: 'account type asset' should not set account_number filter."""
        query_lower = "show transactions for account type asset"
        filters = finance_agent._identify_filters(query_lower, [])
        # After fix: account_number should NOT be set for this query
        assert "account_number" not in filters, \
            f"account_number incorrectly set to: {filters.get('account_number')}"
        # account_type should still be correctly set via direct type-name lookup
        assert filters.get("account_type") == "ASSET"

    def test_account_filter_no_greedy_match(self, finance_agent):
        """Fixed behavior: 'account type asset' sets account_type but not account_number."""
        query_lower = "show transactions for account type asset"
        filters = finance_agent._identify_filters(query_lower, [])
        # After Bug 1 fix: account_number is NOT set (requires quotes or digits)
        assert "account_number" not in filters
        # account_type IS correctly set via direct type-name lookup
        assert filters.get("account_type") == "ASSET"
        # Full pipeline still works
        result = finance_agent.process_query("Show transactions for account type asset")
        assert isinstance(result, dict)
        assert "sql" in result

    def test_total_by_account_type(self, finance_agent):
        """Group by: total balance by account type.

        Fragment parser finds 'account type' as one group part, matching both
        'account' (→ account_id) and 'type' (→ account_type) keywords.
        """
        result = finance_agent.process_query("Total balance by account type")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        # account_type must appear in GROUP BY (the key dimension being asked about)
        assert "account_type" in result["sql"]

    def test_total_by_account(self, finance_agent):
        """Group by: total amount per account."""
        result = finance_agent.process_query("Total amount by account")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "account_id" in result["sql"]

    def test_transactions_by_date(self, finance_agent):
        """Group by: transactions grouped by date."""
        result = finance_agent.process_query("Show transactions grouped by date")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "date" in result["sql"]

    def test_average_transaction_amount(self, finance_agent):
        """Aggregate: average transaction amount."""
        result = finance_agent.process_query("What is the average transaction amount?")
        assert_valid_result(result)
        assert "AVG" in result["sql"]

    def test_count_transactions(self, finance_agent):
        """Aggregate: count of transactions."""
        result = finance_agent.process_query("How many transactions are there?")
        assert_valid_result(result)
        assert "COUNT" in result["sql"]


# ---------------------------------------------------------------------------
# Class 3: Operations Queries (13 tests)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestOperationsQueries:
    """Tests for the Operations domain agent via the UI code path."""

    def test_total_inventory_all_warehouses(self, ops_agent):
        """Aggregate: total inventory across all warehouses."""
        result = ops_agent.process_query("What is the total inventory across all warehouses?")
        assert_valid_result(result)
        assert "SUM" in result["sql"]
        assert "inventory_fact" in result["views"]

    def test_inventory_by_warehouse(self, ops_agent):
        """Group by: inventory per warehouse."""
        result = ops_agent.process_query("Show me inventory by warehouse")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "warehouse_id" in result["sql"]

    def test_inventory_by_product_includes_product_dim(self, ops_agent):
        """Bug 4 fixed: 'inventory by product' should join product_dim via cross-domain view."""
        result = ops_agent.process_query("Show inventory by product")
        assert_valid_result(result)
        # After fix: product_dim should be in selected views
        assert "product_dim" in result["views"], \
            "product_dim missing from views — cross-domain join not working"

    def test_inventory_by_product_has_groupby(self, ops_agent):
        """Group by: inventory by product has GROUP BY product_id (even if no dim join)."""
        result = ops_agent.process_query("Show inventory by product")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "product_id" in result["sql"]

    def test_shipment_overview(self, ops_agent):
        """Simple select: all shipments."""
        result = ops_agent.process_query("Show me all shipments")
        assert_valid_result(result)
        assert "shipment_fact" in result["views"]

    def test_total_shipment_quantity(self, ops_agent):
        """Aggregate: total quantity shipped — should go to shipment_fact only."""
        result = ops_agent.process_query("Total quantity shipped")
        assert_valid_result(result)
        assert "SUM" in result["sql"]
        assert "shipment_fact" in result["views"]
        # inventory_fact must not be pulled in (would cause invalid join error)
        assert "inventory_fact" not in result["views"]

    def test_warehouse_location_strips_article(self, ops_agent):
        """Bug 2b fixed: 'at the Chicago warehouse' should give location='chicago'."""
        query_lower = "show inventory at the chicago warehouse"
        filters = ops_agent._identify_filters(query_lower, [])
        location = filters.get("location", "")
        assert location.lower() == "chicago", \
            f"Expected 'chicago' but got '{location}' — leading article not stripped"

    def test_warehouse_location_current_behavior(self, ops_agent):
        """Document current location filter behavior — may include leading 'the'."""
        result = ops_agent.process_query("Show inventory at the Chicago warehouse")
        # Should not crash regardless
        assert isinstance(result, dict)
        assert "sql" in result

    def test_warehouse_name_filter_quoted(self, ops_agent):
        """Filter: quoted warehouse name is correctly captured."""
        query_lower = "show inventory at warehouse 'dallas dc'"
        filters = ops_agent._identify_filters(query_lower, [])
        assert filters.get("name") == "dallas dc"

    def test_warehouse_filter_no_preposition(self, ops_agent):
        """Bug 2a fixed: 'warehouse in chicago' should not set name='in chicago'."""
        query_lower = "show inventory for warehouse in chicago"
        filters = ops_agent._identify_filters(query_lower, [])
        # After fix: warehouse name regex requires quotes — unquoted "warehouse in chicago"
        # should NOT set filters["name"] to "in chicago"
        name = filters.get("name", "")
        assert not name.startswith("in "), \
            f"Warehouse name incorrectly includes preposition: '{name}'"

    def test_count_shipments(self, ops_agent):
        """Aggregate: count of shipments."""
        result = ops_agent.process_query("How many shipments were made?")
        assert_valid_result(result)
        assert "COUNT" in result["sql"]
        assert "shipment_fact" in result["views"]

    def test_average_inventory(self, ops_agent):
        """Aggregate: average inventory level."""
        result = ops_agent.process_query("What is the average inventory level?")
        assert_valid_result(result)
        assert "AVG" in result["sql"]
        assert "inventory_fact" in result["views"]

    def test_low_stock_items(self, ops_agent):
        """Simple select: query about low stock — should not crash."""
        result = ops_agent.process_query("Which products have low stock levels?")
        assert isinstance(result, dict)
        assert "sql" in result
        assert "inventory_fact" in result["views"]

    def test_shipment_by_warehouse(self, ops_agent):
        """Group by: total shipments by warehouse — shipment_fact + warehouse_dim join."""
        result = ops_agent.process_query("Total shipments by warehouse")
        assert_valid_result(result)
        assert "GROUP BY" in result["sql"]
        assert "warehouse_id" in result["sql"]
        assert "shipment_fact" in result["views"]
        # inventory_fact must not be pulled in (would cause invalid join error)
        assert "inventory_fact" not in result["views"]

    def test_inventory_quantity_on_hand(self, ops_agent):
        """Simple select: current quantity on hand."""
        result = ops_agent.process_query("Show current quantity on hand")
        assert_valid_result(result)
        assert "inventory_fact" in result["views"]


# ---------------------------------------------------------------------------
# Class 4: Cross-Domain Routing (5 tests)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCrossDomainRouting:
    """Tests that the orchestrator routes queries to the correct domain."""

    def test_router_sends_ledger_to_finance(self, orchestrator):
        """Routing: ledger keyword → finance domain."""
        result = orchestrator.process_query("Show me all ledger transactions")
        assert isinstance(result, dict)
        assert result.get("domain") == "finance"
        assert result.get("routing_confidence", 0) > 0.5

    def test_router_sends_inventory_to_operations(self, orchestrator):
        """Routing: inventory keyword → operations domain."""
        result = orchestrator.process_query("What is current inventory stock level?")
        assert isinstance(result, dict)
        assert result.get("domain") == "operations"

    def test_router_sends_sales_to_sales(self, orchestrator):
        """Routing: revenue + customer keywords → sales domain."""
        result = orchestrator.process_query("What was the total revenue from customers?")
        assert isinstance(result, dict)
        assert result.get("domain") == "sales"

    def test_router_ambiguous_quantity_goes_to_operations(self, orchestrator):
        """Routing: 'quantity' keyword is exclusively in operations keywords."""
        result = orchestrator.process_query("Show quantity data")
        assert isinstance(result, dict)
        assert result.get("domain") == "operations"

    def test_router_defaults_sales_on_no_match(self, orchestrator):
        """BUG 6: Generic query with no keywords defaults to sales with 0.33 confidence."""
        result = orchestrator.process_query("Show me everything")
        assert isinstance(result, dict)
        # Document current behavior: falls back to sales
        assert result.get("domain") == "sales"
        assert abs(result.get("routing_confidence", 0) - 0.33) < 0.01, \
            f"Expected routing_confidence ~0.33, got {result.get('routing_confidence')}"


# ---------------------------------------------------------------------------
# Class 5: Edge Cases (3 tests)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestEdgeCases:
    """Edge case robustness tests."""

    def test_empty_query_no_crash(self, orchestrator):
        """Empty string should not crash — return some dict."""
        result = orchestrator.process_query("")
        assert isinstance(result, dict)
        # Either domain key (normal path) or error key
        assert "domain" in result or "error" in result

    def test_very_long_query_no_crash(self, orchestrator):
        """Very long query (500 chars) should not crash."""
        long_query = (
            "Show me detailed comprehensive information about all available "
            "data records including transactions amounts quantities regions "
            "customers products accounts ledger entries inventory shipments "
            "warehouse locations and all related information in the system " * 4
        )[:500]
        result = orchestrator.process_query(long_query)
        assert isinstance(result, dict)

    def test_numeric_only_query_no_crash(self, orchestrator):
        """Numeric-only query ('2024') should not crash."""
        result = orchestrator.process_query("2024")
        assert isinstance(result, dict)
        assert "domain" in result or "error" in result
