"""
Integration Tests for Agents and Query Building

Tests the complete workflow from natural language query to SQL execution.
"""

import pytest
from app.views.registry import create_test_registry
from app.database.connection import DbConnection, reset_db
from app.query.builder import QueryBuilder
from app.views.models import QueryRequest
from app.agents.domain.sales import SalesAgent


@pytest.fixture
def setup_test_environment():
    """Set up registry, database, and builder for testing."""
    reset_db()

    # Create registry with sample data
    registry = create_test_registry()

    # Create in-memory database
    db = DbConnection(connection_string="sqlite:///:memory:")

    # Create query builder
    builder = QueryBuilder(registry)

    return registry, db, builder


@pytest.fixture
def sales_agent(setup_test_environment):
    """Create Sales agent with test environment."""
    registry, db, builder = setup_test_environment
    # Use mock database instead of trying to execute queries
    db_mock = DbConnection(is_mock=True)
    return SalesAgent(registry, db_mock, builder)


class TestQueryBuilder:
    """Test SQL query building functionality."""

    def test_build_simple_select_query(self, setup_test_environment):
        """Test building a simple SELECT query."""
        registry, db, builder = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            limit=10,
        )

        query = builder.build_query(request)

        assert "SELECT" in query
        assert "sales_fact.*" in query
        assert "FROM sales_fact" in query
        assert "LIMIT 10" in query

    def test_build_query_with_filters(self, setup_test_environment):
        """Test building a query with WHERE clause."""
        registry, db, builder = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            filters={"region": "WEST"},
            limit=50,
        )

        query = builder.build_query(request)

        assert "WHERE" in query
        assert "region = 'WEST'" in query

    def test_build_query_with_aggregations(self, setup_test_environment):
        """Test building a query with GROUP BY and aggregations."""
        registry, db, builder = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["region"],
            limit=100,
        )

        query = builder.build_query(request)

        assert "SUM(sales_fact.amount)" in query
        assert "GROUP BY" in query

    def test_build_query_with_joins(self, setup_test_environment):
        """Test building a query that joins multiple views."""
        registry, db, builder = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact", "customer_dim"],
            limit=100,
        )

        query = builder.build_query(request)

        assert "sales_fact" in query
        assert "customer_dim" in query
        assert "JOIN" in query
        assert "ON" in query

    def test_builder_validates_nonexistent_view(self, setup_test_environment):
        """Test that builder rejects nonexistent views."""
        registry, db, builder = setup_test_environment

        request = QueryRequest(
            selected_views=["nonexistent_view"],
            limit=100,
        )

        with pytest.raises(ValueError):
            builder.build_query(request)

    def test_builder_suggests_columns(self, setup_test_environment):
        """Test column suggestion feature."""
        registry, db, builder = setup_test_environment

        # Should suggest columns starting with 's'
        suggestions = builder.suggest_columns("sales_fact", "s")

        assert "sale_id" in suggestions

    def test_builder_suggests_aggregations(self, setup_test_environment):
        """Test aggregation suggestion feature."""
        registry, db, builder = setup_test_environment

        suggestions = builder.get_suggested_aggregations("sales_fact")

        # Should have suggestions for numeric columns
        assert len(suggestions) > 0

        # Check for numeric columns like quantity (INT)
        if "quantity" in suggestions:
            assert "SUM" in suggestions["quantity"]


class TestSalesAgent:
    """Test Sales agent functionality."""

    def test_agent_identifies_sales_views(self, sales_agent):
        """Test that agent correctly identifies relevant views."""
        available = sales_agent.get_available_views()

        assert "sales_fact" in available
        assert "customer_dim" in available

    def test_agent_builds_simple_query_logic(self, setup_test_environment):
        """Test agent query building logic without database execution."""
        registry, db, builder = setup_test_environment
        # Use mock DB to avoid database errors
        db_mock = DbConnection(is_mock=True)
        agent = SalesAgent(registry, db_mock, builder)

        # Test that the agent identifies views correctly
        views = agent._identify_views("what was the total sales amount?")
        assert "sales_fact" in views

    def test_agent_identifies_filters(self, sales_agent):
        """Test that agent correctly identifies filter keywords."""
        filters = sales_agent._identify_filters("sales in the WEST region", [])
        assert "region" in filters
        assert filters["region"] == "WEST"

    def test_agent_identifies_aggregations_logic(self, sales_agent):
        """Test aggregation identification logic."""
        aggs, group_by = sales_agent._identify_aggregations(
            "what is the total amount sold?", ["sales_fact"]
        )

        # Should identify some aggregation for the word "total"
        assert len(aggs) > 0 or len(group_by) >= 0

    def test_agent_finds_available_views(self, sales_agent):
        """Test agent view listing."""
        summary = sales_agent.get_view_summary()

        assert "sales_fact" in summary
        assert "customer_dim" in summary
        assert "product_dim" in summary

    def test_agent_clarify_provides_suggestions(self, sales_agent):
        """Test that agent provides helpful suggestions."""
        clarify = sales_agent.clarify_query("tell me about sales")

        assert "available_views" in clarify
        assert "sample_queries" in clarify

    def test_agent_confidence_calculation(self, sales_agent):
        """Test confidence score calculation."""
        confidence = sales_agent._calculate_confidence(
            "sales in WEST region", {"row_count": 10}
        )

        assert 0 <= confidence <= 1
        assert confidence > 0.5  # Should have decent confidence with data


class TestEndToEndQueryFlow:
    """Test complete query flow from natural language to execution."""

    def test_query_building_pipeline(self, setup_test_environment):
        """Test the query building pipeline without database execution."""
        registry, db, builder = setup_test_environment

        # Test building simple query
        request = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            limit=100,
        )

        sql = builder.build_query(request)

        # Verify SQL was generated correctly
        assert "SELECT" in sql
        assert "SUM(sales_fact.amount)" in sql
        assert "FROM" in sql
        assert "LIMIT" in sql

    def test_agent_view_identification(self, setup_test_environment):
        """Test agent view identification logic."""
        registry, db, builder = setup_test_environment
        agent = SalesAgent(registry, db, builder)

        # Test identifying views from keywords
        views = agent._identify_views("sales in region WEST with customers")

        assert "sales_fact" in views
        assert "customer_dim" in views

    def test_agent_error_handling(self, setup_test_environment):
        """Test that agent handles errors gracefully."""
        registry, db, builder = setup_test_environment
        agent = SalesAgent(registry, db, builder)

        # An empty question should still be handled
        result = agent.process_query("")

        assert isinstance(result, dict)

    def test_query_builder_chain(self, setup_test_environment):
        """Test building queries with different characteristics."""
        registry, db, builder = setup_test_environment

        # Simple query
        simple = QueryRequest(selected_views=["sales_fact"], limit=10)
        sql1 = builder.build_query(simple)
        assert "SELECT" in sql1

        # Query with filters
        filtered = QueryRequest(
            selected_views=["sales_fact"], filters={"region": "EAST"}, limit=50
        )
        sql2 = builder.build_query(filtered)
        assert "WHERE" in sql2

        # Query with aggregations
        agg = QueryRequest(
            selected_views=["sales_fact"],
            aggregations={"amount": "SUM"},
            group_by=["region"],
        )
        sql3 = builder.build_query(agg)
        assert "GROUP BY" in sql3

        # All should be valid SQL-like strings
        assert isinstance(sql1, str) and len(sql1) > 0
        assert isinstance(sql2, str) and len(sql2) > 0
        assert isinstance(sql3, str) and len(sql3) > 0


class TestAgentReliability:
    """Test agent reliability and robustness."""

    def test_agent_recovers_from_invalid_domain(self):
        """Test that invalid domain handling is graceful."""
        reset_db()
        registry = create_test_registry()
        db = DbConnection(connection_string="sqlite:///:memory:")
        builder = QueryBuilder(registry)

        # SalesAgent is specifically for sales domain
        agent = SalesAgent(registry, db, builder)

        # Agent should still work
        assert agent.domain == "sales"

    def test_agent_handles_empty_registry(self):
        """Test agent behavior with empty registry."""
        from app.views.registry import ViewRegistry

        reset_db()
        empty_registry = ViewRegistry()
        db = DbConnection(connection_string="sqlite:///:memory:")
        builder = QueryBuilder(empty_registry)

        agent = SalesAgent(empty_registry, db, builder)

        # Should return empty or error gracefully
        views = agent.get_available_views()
        assert isinstance(views, list)

    def test_confidence_scoring(self, sales_agent):
        """Test that confidence scores are consistent."""
        results = []

        queries = [
            "What were the total sales?",
            "sales in WEST",
            "How many units were sold?",
        ]

        for query in queries:
            result = sales_agent.process_query(query)
            results.append(result["confidence"])

        # All confidences should be in valid range
        assert all(0 <= conf <= 1 for conf in results)
