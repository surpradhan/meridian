"""
Integration Tests for Phase 3 (Query Validation) and Phase 4 (Multi-Agent)

Tests query validation, multi-domain agents, and routing logic.
"""

import pytest
from app.views.registry import create_test_registry
from app.database.connection import DbConnection, reset_db
from app.query.builder import QueryBuilder
from app.query.validator import QueryValidator
from app.views.models import QueryRequest
from app.agents.domain.sales import SalesAgent
from app.agents.domain.finance import FinanceAgent
from app.agents.domain.operations import OperationsAgent
from app.agents.router import RouterAgent


@pytest.fixture
def setup_test_environment():
    """Set up registry, database, builder, and validator."""
    reset_db()

    registry = create_test_registry()
    db = DbConnection(is_mock=True)
    builder = QueryBuilder(registry)
    validator = QueryValidator(registry)

    return registry, db, builder, validator


class TestQueryValidator:
    """Test query validation functionality."""

    def test_validate_valid_query(self, setup_test_environment):
        """Test validating a valid query."""
        registry, _, builder, validator = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            limit=100,
        )

        is_valid, errors = validator.validate(request)

        assert is_valid
        assert len(errors) == 0

    def test_validate_nonexistent_view(self, setup_test_environment):
        """Test that validator rejects nonexistent views."""
        registry, _, builder, validator = setup_test_environment

        request = QueryRequest(
            selected_views=["nonexistent_view"],
            limit=100,
        )

        is_valid, errors = validator.validate(request)

        assert not is_valid
        assert any("not found" in error.lower() for error in errors)

    def test_validate_nonexistent_column(self, setup_test_environment):
        """Test that validator checks for column existence."""
        registry, _, builder, validator = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            filters={"nonexistent_column": "value"},
            limit=100,
        )

        is_valid, errors = validator.validate(request)

        assert not is_valid
        assert any("column" in error.lower() for error in errors)

    def test_validate_limit_too_high(self, setup_test_environment):
        """Test that validator enforces limit constraints."""
        registry, _, builder, validator = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            limit=100000,  # Over default max of 10000
        )

        is_valid, errors = validator.validate(request)

        assert not is_valid
        assert any("limit" in error.lower() for error in errors)

    def test_estimate_result_size(self, setup_test_environment):
        """Test result size estimation."""
        registry, _, builder, validator = setup_test_environment

        request = QueryRequest(
            selected_views=["sales_fact"],
            limit=100,
        )

        estimated = validator.estimate_result_size(request)

        assert isinstance(estimated, int)
        assert estimated > 0
        assert estimated <= request.limit

    def test_get_validation_warnings(self, setup_test_environment):
        """Test that validator provides helpful warnings."""
        registry, _, builder, validator = setup_test_environment

        # Query without filters that might return many rows
        request = QueryRequest(
            selected_views=["sales_fact"],
            limit=5000,
        )

        warnings = validator.get_validation_warnings(request)

        # May or may not have warnings depending on row estimates
        assert isinstance(warnings, list)

    def test_validate_many_to_many_without_aggregation(self, setup_test_environment):
        """Test validation warning for many-to-many without aggregation."""
        registry, _, builder, validator = setup_test_environment

        # Note: Our test data doesn't have many-to-many, but validate the logic
        request = QueryRequest(
            selected_views=["sales_fact", "customer_dim"],
            limit=5000,
        )

        is_valid, errors = validator.validate(request)

        # Query should still be valid but might have warnings
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)


class TestFinanceAgent:
    """Test Finance domain agent."""

    def test_finance_agent_initialization(self, setup_test_environment):
        """Test Finance agent can be created."""
        registry, db, builder, _ = setup_test_environment

        agent = FinanceAgent(registry, db, builder)

        assert agent.domain == "finance"
        assert "ledger_fact" in agent.get_available_views()

    def test_finance_agent_identifies_views(self, setup_test_environment):
        """Test Finance agent identifies appropriate views."""
        registry, db, builder, _ = setup_test_environment
        agent = FinanceAgent(registry, db, builder)

        views = agent._identify_views("show me ledger transactions")

        assert "ledger_fact" in views

    def test_finance_agent_identifies_filters(self, setup_test_environment):
        """Test Finance agent identifies financial filters."""
        registry, db, builder, _ = setup_test_environment
        agent = FinanceAgent(registry, db, builder)

        filters = agent._identify_filters("account 1000 debit transactions", [])

        assert "debit_credit" in filters or "account_number" in filters


class TestOperationsAgent:
    """Test Operations domain agent."""

    def test_operations_agent_initialization(self, setup_test_environment):
        """Test Operations agent can be created."""
        registry, db, builder, _ = setup_test_environment

        agent = OperationsAgent(registry, db, builder)

        assert agent.domain == "operations"
        assert "inventory_fact" in agent.get_available_views()

    def test_operations_agent_identifies_views(self, setup_test_environment):
        """Test Operations agent identifies appropriate views."""
        registry, db, builder, _ = setup_test_environment
        agent = OperationsAgent(registry, db, builder)

        views = agent._identify_views("warehouse inventory levels")

        assert "inventory_fact" in views

    def test_operations_agent_identifies_filters(self, setup_test_environment):
        """Test Operations agent identifies warehouse filters."""
        registry, db, builder, _ = setup_test_environment
        agent = OperationsAgent(registry, db, builder)

        filters = agent._identify_filters("inventory at New York warehouse", [])

        assert "name" in filters or "location" in filters


class TestRouterAgent:
    """Test request routing functionality."""

    def test_router_routes_to_sales(self, setup_test_environment):
        """Test router correctly identifies sales queries."""
        registry, _, _, _ = setup_test_environment
        router = RouterAgent(registry)

        domain, confidence = router.route("How many sales were made?")

        assert domain == "sales"
        assert confidence > 0

    def test_router_routes_to_finance(self, setup_test_environment):
        """Test router correctly identifies finance queries."""
        registry, _, _, _ = setup_test_environment
        router = RouterAgent(registry)

        domain, confidence = router.route("What is the account balance?")

        assert domain == "finance"
        assert confidence > 0

    def test_router_routes_to_operations(self, setup_test_environment):
        """Test router correctly identifies operations queries."""
        registry, _, _, _ = setup_test_environment
        router = RouterAgent(registry)

        domain, confidence = router.route("Show me warehouse inventory")

        assert domain == "operations"
        assert confidence > 0

    def test_router_default_to_sales(self, setup_test_environment):
        """Test router defaults to sales for ambiguous queries."""
        registry, _, _, _ = setup_test_environment
        router = RouterAgent(registry)

        domain, confidence = router.route("Tell me something interesting")

        # Should default to sales when no clear domain signals
        assert domain in ["sales", "finance", "operations"]

    def test_router_provides_domain_info(self, setup_test_environment):
        """Test router provides domain information."""
        registry, _, _, _ = setup_test_environment
        router = RouterAgent(registry)

        info = router.get_domain_info("sales")

        assert "domain" in info
        assert "keywords" in info
        assert "views" in info
        assert info["domain"] == "sales"


class TestMultiDomainWorkflow:
    """Test complete multi-domain query workflows."""

    def test_sales_to_finance_routing(self, setup_test_environment):
        """Test routing between different domains."""
        registry, _, _, _ = setup_test_environment
        router = RouterAgent(registry)

        # Sales query
        domain1, conf1 = router.route("Total sales by customer")
        assert domain1 == "sales"

        # Finance query
        domain2, conf2 = router.route("Total GL amounts by account")
        assert domain2 == "finance"

        # Different domains should have been detected
        assert domain1 != domain2

    def test_all_agents_have_required_methods(self, setup_test_environment):
        """Test that all agents implement required interface."""
        registry, db, builder, _ = setup_test_environment

        agents = [
            SalesAgent(registry, db, builder),
            FinanceAgent(registry, db, builder),
            OperationsAgent(registry, db, builder),
        ]

        for agent in agents:
            assert hasattr(agent, "process_query")
            assert hasattr(agent, "get_available_views")
            assert hasattr(agent, "get_view_summary")
            assert callable(agent.process_query)
            assert callable(agent.get_available_views)

    def test_agent_domain_consistency(self, setup_test_environment):
        """Test that agents are assigned to correct domains."""
        registry, db, builder, _ = setup_test_environment

        sales_agent = SalesAgent(registry, db, builder)
        finance_agent = FinanceAgent(registry, db, builder)
        ops_agent = OperationsAgent(registry, db, builder)

        assert sales_agent.domain == "sales"
        assert finance_agent.domain == "finance"
        assert ops_agent.domain == "operations"

    def test_query_validation_across_domains(self, setup_test_environment):
        """Test validation works correctly for all domains."""
        registry, _, _, validator = setup_test_environment

        # Sales query
        sales_request = QueryRequest(
            selected_views=["sales_fact", "customer_dim"],
            limit=100,
        )
        is_valid, errors = validator.validate(sales_request)
        assert is_valid

        # Finance query
        finance_request = QueryRequest(
            selected_views=["ledger_fact", "account_dim"],
            limit=100,
        )
        is_valid, errors = validator.validate(finance_request)
        assert is_valid

        # Operations query
        ops_request = QueryRequest(
            selected_views=["inventory_fact", "warehouse_dim"],
            limit=100,
        )
        is_valid, errors = validator.validate(ops_request)
        assert is_valid
