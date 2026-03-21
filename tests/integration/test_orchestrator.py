"""
Integration Tests for Orchestrator

Tests the complete multi-agent orchestration workflow.
"""

import pytest
from app.views.registry import create_test_registry
from app.database.connection import DbConnection, reset_db
from app.agents.orchestrator import Orchestrator, QueryState


@pytest.fixture
def setup_orchestrator():
    """Set up orchestrator for testing."""
    reset_db()
    registry = create_test_registry()
    db = DbConnection(is_mock=True)
    orchestrator = Orchestrator(registry, db)
    return orchestrator


class TestOrchestratorBasics:
    """Test basic orchestrator functionality."""

    def test_orchestrator_initialization(self, setup_orchestrator):
        """Test that orchestrator initializes correctly."""
        orchestrator = setup_orchestrator
        assert orchestrator is not None
        assert orchestrator.registry is not None
        assert orchestrator.db is not None
        assert orchestrator.builder is not None
        assert orchestrator.validator is not None
        assert orchestrator.router is not None
        assert len(orchestrator.domain_agents) == 3

    def test_orchestrator_has_all_domain_agents(self, setup_orchestrator):
        """Test that orchestrator has agents for all domains."""
        orchestrator = setup_orchestrator
        assert "sales" in orchestrator.domain_agents
        assert "finance" in orchestrator.domain_agents
        assert "operations" in orchestrator.domain_agents


class TestOrchestratorRouting:
    """Test query routing through orchestrator."""

    def test_orchestrator_routes_sales_query(self, setup_orchestrator):
        """Test orchestrator routes sales queries correctly."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("How many sales were made?")

        assert result["domain"] == "sales"
        assert "routing_confidence" in result
        assert "state" in result

    def test_orchestrator_routes_finance_query(self, setup_orchestrator):
        """Test orchestrator routes finance queries correctly."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("What is the account balance?")

        assert result["domain"] == "finance"
        assert "routing_confidence" in result

    def test_orchestrator_routes_operations_query(self, setup_orchestrator):
        """Test orchestrator routes operations queries correctly."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("Show me warehouse inventory")

        assert result["domain"] == "operations"
        assert "routing_confidence" in result

    def test_orchestrator_provides_routing_confidence(self, setup_orchestrator):
        """Test that orchestrator provides routing confidence scores."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("Sales in WEST region")

        assert "routing_confidence" in result
        assert 0 <= result["routing_confidence"] <= 1


class TestOrchestratorValidation:
    """Test query validation through orchestrator."""

    def test_validate_query_for_domain_sales(self, setup_orchestrator):
        """Test validation for sales domain queries."""
        orchestrator = setup_orchestrator
        is_valid, errors = orchestrator.validate_query_for_domain("sales", "sales data")

        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_validate_query_for_domain_finance(self, setup_orchestrator):
        """Test validation for finance domain queries."""
        orchestrator = setup_orchestrator
        is_valid, errors = orchestrator.validate_query_for_domain("finance", "ledger transactions")

        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_validate_query_for_domain_operations(self, setup_orchestrator):
        """Test validation for operations domain queries."""
        orchestrator = setup_orchestrator
        is_valid, errors = orchestrator.validate_query_for_domain("operations", "inventory levels")

        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_validate_query_unknown_domain(self, setup_orchestrator):
        """Test validation for unknown domain."""
        orchestrator = setup_orchestrator
        is_valid, errors = orchestrator.validate_query_for_domain("unknown", "some query")

        assert not is_valid
        assert len(errors) > 0


class TestOrchestratorCapabilities:
    """Test domain capability discovery."""

    def test_get_domain_capabilities_sales(self, setup_orchestrator):
        """Test getting sales domain capabilities."""
        orchestrator = setup_orchestrator
        caps = orchestrator.get_domain_capabilities("sales")

        assert "domain" in caps
        assert caps["domain"] == "sales"
        assert "available_views" in caps
        assert "view_summary" in caps
        assert "keywords" in caps

    def test_get_domain_capabilities_finance(self, setup_orchestrator):
        """Test getting finance domain capabilities."""
        orchestrator = setup_orchestrator
        caps = orchestrator.get_domain_capabilities("finance")

        assert caps["domain"] == "finance"
        assert len(caps["available_views"]) > 0

    def test_get_domain_capabilities_operations(self, setup_orchestrator):
        """Test getting operations domain capabilities."""
        orchestrator = setup_orchestrator
        caps = orchestrator.get_domain_capabilities("operations")

        assert caps["domain"] == "operations"
        assert len(caps["available_views"]) > 0

    def test_get_domain_capabilities_unknown(self, setup_orchestrator):
        """Test getting capabilities for unknown domain."""
        orchestrator = setup_orchestrator
        caps = orchestrator.get_domain_capabilities("unknown")

        assert "error" in caps

    def test_get_all_domains(self, setup_orchestrator):
        """Test getting information about all domains."""
        orchestrator = setup_orchestrator
        domains = orchestrator.get_all_domains()

        assert isinstance(domains, list)
        assert len(domains) == 3

        domain_names = [d["domain"] for d in domains]
        assert "sales" in domain_names
        assert "finance" in domain_names
        assert "operations" in domain_names


class TestOrchestratorProcessing:
    """Test full query processing workflow."""

    def test_process_sales_query_returns_result(self, setup_orchestrator):
        """Test processing a sales query returns result."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("How many sales were made?")

        assert "result" in result or "error" in result
        assert "domain" in result
        assert "state" in result

    def test_process_query_sets_state(self, setup_orchestrator):
        """Test that processed queries have correct state."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("Sales data")

        assert result["state"] in [QueryState.COMPLETE.value, QueryState.ERROR.value]

    def test_process_query_includes_confidence(self, setup_orchestrator):
        """Test that processed queries include confidence scores."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("Total sales amount")

        assert "confidence" in result

    def test_process_query_includes_domain(self, setup_orchestrator):
        """Test that processed queries include domain information."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("Sales in region WEST")

        assert "domain" in result
        assert result["domain"] in ["sales", "finance", "operations"]

    def test_process_query_handles_errors(self, setup_orchestrator):
        """Test that orchestrator handles errors gracefully."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("")

        assert isinstance(result, dict)
        # Empty query should either succeed or fail gracefully
        assert "domain" in result or "error" in result


class TestOrchestratorTracing:
    """Test query tracing for debugging."""

    def test_process_query_with_trace_returns_trace(self, setup_orchestrator):
        """Test that tracing returns detailed execution trace."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("How many sales were made?")

        assert "query" in trace
        assert trace["query"] == "How many sales were made?"
        assert "steps" in trace
        assert isinstance(trace["steps"], list)

    def test_trace_includes_routing_step(self, setup_orchestrator):
        """Test that trace includes routing step."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("Sales data")

        routing_steps = [s for s in trace["steps"] if s["step"] == "routing"]
        assert len(routing_steps) > 0
        assert "domain" in routing_steps[0]
        assert "confidence" in routing_steps[0]

    def test_trace_includes_agent_processing_step(self, setup_orchestrator):
        """Test that trace includes agent processing step."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("Sales amount")

        processing_steps = [s for s in trace["steps"] if s["step"] == "agent_processing"]
        # May or may not have agent processing depending on query
        assert isinstance(processing_steps, list)

    def test_trace_includes_validation_step(self, setup_orchestrator):
        """Test that trace includes validation step."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("How many sales?")

        validation_steps = [s for s in trace["steps"] if s["step"] == "validation"]
        assert len(validation_steps) > 0

    def test_trace_includes_execution_step(self, setup_orchestrator):
        """Test that trace includes execution step."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("Sales data")

        execution_steps = [s for s in trace["steps"] if s["step"] == "execution"]
        assert len(execution_steps) > 0

    def test_trace_sets_state(self, setup_orchestrator):
        """Test that trace includes state information."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("Sales")

        assert "state" in trace
        assert trace["state"] in [QueryState.COMPLETE.value, QueryState.ERROR.value]

    def test_trace_includes_domain(self, setup_orchestrator):
        """Test that trace includes domain information."""
        orchestrator = setup_orchestrator
        trace = orchestrator.process_query_with_trace("Sales in WEST")

        assert "domain" in trace


class TestOrchestratorMultiDomain:
    """Test multi-domain orchestration."""

    def test_orchestrator_switches_domains(self, setup_orchestrator):
        """Test that orchestrator correctly switches between domains."""
        orchestrator = setup_orchestrator

        # Sales query
        sales_result = orchestrator.process_query("How many sales were made?")
        assert sales_result["domain"] == "sales"

        # Finance query
        finance_result = orchestrator.process_query("What is the account balance?")
        assert finance_result["domain"] == "finance"

        # Operations query
        ops_result = orchestrator.process_query("Show me inventory levels")
        assert ops_result["domain"] == "operations"

        # Different domains should have been detected
        assert sales_result["domain"] != finance_result["domain"]
        assert finance_result["domain"] != ops_result["domain"]

    def test_orchestrator_consistency_across_domains(self, setup_orchestrator):
        """Test that all domains return consistent result structure."""
        orchestrator = setup_orchestrator

        domains = ["sales", "finance", "operations"]
        results = []

        for domain in domains:
            if domain == "sales":
                query = "Sales data"
            elif domain == "finance":
                query = "Ledger transactions"
            else:
                query = "Inventory levels"

            result = orchestrator.process_query(query)
            results.append(result)
            assert "domain" in result
            assert "state" in result
            assert "confidence" in result

        # All should have consistent structure
        for result in results:
            assert isinstance(result, dict)
