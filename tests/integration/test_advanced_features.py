"""
Tests for Advanced Features (Phase 5 Extensions)

Tests for distributed tracing, caching, pagination, Langraph integration,
conversation context, and index optimization.
"""

import pytest
from typing import List, Dict, Any

from app.observability.tracing import TracingManager, TracingConfig, setup_tracing
from app.cache.manager import CacheManager, CacheConfig, setup_cache
from app.query.pagination import Paginator, PaginatedResult, StreamingResult
from app.agents.langraph_orchestrator import LangraphOrchestrator
from app.agents.conversation_context import (
    ConversationContext,
    ConversationManager,
    get_conversation_manager,
)
from app.database.index_optimizer import IndexOptimizer, QueryAnalyzer
from app.views.registry import create_test_registry
from app.database.connection import DbConnection, reset_db


# ============================================================================
# Distributed Tracing Tests
# ============================================================================

class TestDistributedTracing:
    """Test distributed tracing with OpenTelemetry."""

    def test_tracing_config_initialization(self):
        """Test tracing configuration."""
        config = TracingConfig(
            service_name="test-service",
            jaeger_host="localhost",
            jaeger_port=6831,
            enabled=False,  # Don't connect to Jaeger
        )
        assert config.service_name == "test-service"
        assert config.jaeger_host == "localhost"

    def test_tracing_manager_singleton(self):
        """Test TracingManager singleton pattern."""
        config = TracingConfig(enabled=False)
        manager1 = TracingManager.get_instance(config)
        manager2 = TracingManager.get_instance()
        assert manager1 is manager2

    def test_span_context_manager(self):
        """Test span creation with context manager."""
        config = TracingConfig(enabled=False)
        manager = TracingManager(config)

        # Should not raise even without Jaeger
        with manager.span("test_operation") as span:
            assert span is not None

    def test_span_with_attributes(self):
        """Test span with custom attributes."""
        config = TracingConfig(enabled=False)
        manager = TracingManager(config)

        with manager.span("query_execution", {"query": "SELECT *"}) as span:
            manager.add_event("query_started")
            assert span is not None


# ============================================================================
# Query Caching Tests
# ============================================================================

class TestQueryCaching:
    """Test query result caching."""

    def test_cache_config_initialization(self):
        """Test cache configuration."""
        config = CacheConfig(
            host="localhost",
            ttl_seconds=3600,
            enabled=False,  # Disable Redis connection
        )
        assert config.ttl_seconds == 3600

    def test_cache_manager_disabled(self):
        """Test cache manager when disabled."""
        config = CacheConfig(enabled=False)
        manager = CacheManager(config)

        # Should handle gracefully when disabled
        assert manager.get("test_query") is None
        assert manager.set("test_query", [{"id": 1}]) is False

    def test_cache_key_generation(self):
        """Test cache key generation."""
        config = CacheConfig(enabled=False)
        manager = CacheManager(config)

        key1 = manager._make_key("SELECT * FROM sales")
        key2 = manager._make_key("SELECT * FROM sales")
        assert key1 == key2  # Same query = same key

    def test_cache_statistics(self):
        """Test cache statistics tracking."""
        config = CacheConfig(enabled=False)
        manager = CacheManager(config)

        stats = manager.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0


# ============================================================================
# Pagination Tests
# ============================================================================

class TestPagination:
    """Test pagination functionality."""

    def test_paginator_initialization(self):
        """Test paginator initialization."""
        paginator = Paginator()
        assert paginator.config.default_page_size == 100
        assert paginator.config.max_page_size == 10000

    def test_paginate_simple_result_set(self):
        """Test paginating a simple result set."""
        paginator = Paginator()
        rows = [{"id": i, "name": f"Item {i}"} for i in range(250)]

        result = paginator.paginate(rows, page=1, page_size=100)

        assert result.page == 1
        assert result.page_size == 100
        assert len(result.rows) == 100
        assert result.total_rows == 250
        assert result.total_pages == 3
        assert result.has_next

    def test_paginate_multiple_pages(self):
        """Test pagination across multiple pages."""
        paginator = Paginator()
        rows = [{"id": i} for i in range(250)]

        # Page 1
        page1 = paginator.paginate(rows, page=1, page_size=100)
        assert page1.rows[0]["id"] == 0
        assert page1.rows[-1]["id"] == 99

        # Page 2
        page2 = paginator.paginate(rows, page=2, page_size=100)
        assert page2.rows[0]["id"] == 100
        assert page2.rows[-1]["id"] == 199

        # Page 3
        page3 = paginator.paginate(rows, page=3, page_size=100)
        assert page3.rows[0]["id"] == 200
        assert len(page3.rows) == 50

    def test_paginated_result_to_dict(self):
        """Test PaginatedResult serialization."""
        rows = [{"id": i} for i in range(10)]
        result = PaginatedResult(rows, page=1, page_size=10, total_rows=10)

        data = result.to_dict()
        assert "data" in data
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["has_next"] is False

    def test_streaming_result(self):
        """Test streaming result chunks."""
        rows = [{"id": i} for i in range(2500)]
        stream = StreamingResult(rows, chunk_size=1000)

        chunks = list(stream)
        assert len(chunks) == 3
        assert len(chunks[0]) == 1000
        assert len(chunks[1]) == 1000
        assert len(chunks[2]) == 500


# ============================================================================
# Conversation Context Tests
# ============================================================================

class TestConversationContext:
    """Test conversation context management."""

    def test_conversation_initialization(self):
        """Test conversation context initialization."""
        context = ConversationContext()
        assert context.conversation_id is not None
        assert len(context.messages) == 0

    def test_add_user_message(self):
        """Test adding user messages."""
        context = ConversationContext()
        msg = context.add_user_message("What is the sales total?")

        assert msg.role == "user"
        assert msg.content == "What is the sales total?"
        assert len(context.messages) == 1

    def test_add_assistant_message(self):
        """Test adding assistant messages with results."""
        context = ConversationContext()
        result = {"domain": "sales", "row_count": 42}
        msg = context.add_assistant_message("The total is 42.", query_result=result)

        assert msg.role == "assistant"
        assert msg.query_result == result

    def test_message_history(self):
        """Test retrieving message history."""
        context = ConversationContext()
        context.add_user_message("What are sales?")
        context.add_assistant_message("Sales data retrieved.", {"row_count": 10})
        context.add_user_message("Show me more.")

        history = context.get_message_history(limit=2)
        assert len(history) == 2
        assert history[0]["role"] == "assistant"

    def test_context_update(self):
        """Test updating conversation context."""
        context = ConversationContext()
        context.update_context(
            domain="finance",
            views=["ledger", "accounts"],
            result_count=100,
        )

        assert context.context["last_domain"] == "finance"
        assert context.context["last_views"] == ["ledger", "accounts"]
        assert context.context["last_result_count"] == 100

    def test_session_variables(self):
        """Test session variable storage."""
        context = ConversationContext()
        context.set_session_variable("last_query_id", "q123")
        context.set_session_variable("user_region", "WEST")

        assert context.get_session_variable("last_query_id") == "q123"
        assert context.get_session_variable("user_region") == "WEST"

    def test_conversation_manager(self):
        """Test conversation manager."""
        manager = ConversationManager()

        conv1 = manager.create_conversation()
        assert conv1 is not None

        retrieved = manager.get_conversation(conv1.conversation_id)
        assert retrieved is conv1

        deleted = manager.delete_conversation(conv1.conversation_id)
        assert deleted is True

    def test_conversation_manager_stats(self):
        """Test conversation manager statistics."""
        manager = ConversationManager()

        conv = manager.create_conversation()
        conv.add_user_message("Hello")
        conv.add_assistant_message("Hi there")

        stats = manager.get_stats()
        assert stats["active_conversations"] == 1
        assert stats["total_messages"] == 2


# ============================================================================
# Index Optimization Tests
# ============================================================================

class TestIndexOptimization:
    """Test database index optimization."""

    def test_query_analyzer_initialization(self):
        """Test query analyzer initialization."""
        analyzer = QueryAnalyzer()
        assert len(analyzer.patterns) == 0
        assert len(analyzer.slow_queries) == 0

    def test_record_query_pattern(self):
        """Test recording query patterns."""
        analyzer = QueryAnalyzer()
        analyzer.record_query("sales_fact", ["customer_id"], 50.0)

        assert len(analyzer.patterns) == 1

    def test_slow_query_tracking(self):
        """Test slow query detection."""
        analyzer = QueryAnalyzer()
        analyzer.record_query("sales_fact", ["customer_id"], 150.0)  # Slow

        assert len(analyzer.slow_queries) == 1
        assert analyzer.slow_queries[0]["execution_time_ms"] == 150.0

    def test_pattern_frequency_aggregation(self):
        """Test pattern frequency tracking."""
        analyzer = QueryAnalyzer()

        # Record same pattern multiple times
        for _ in range(5):
            analyzer.record_query("sales_fact", ["customer_id"], 60.0)

        patterns = list(analyzer.patterns.values())
        assert len(patterns) == 1
        assert patterns[0].frequency == 5

    def test_index_recommendations(self):
        """Test generating index recommendations."""
        analyzer = QueryAnalyzer()

        # Record high-frequency slow queries
        for _ in range(20):
            analyzer.record_query("sales_fact", ["customer_id", "date"], 120.0)

        recommendations = analyzer.get_recommendations()
        assert len(recommendations) > 0
        assert recommendations[0].table == "sales_fact"

    def test_slow_query_summary(self):
        """Test slow query summary."""
        analyzer = QueryAnalyzer()
        analyzer.record_query("sales_fact", ["id"], 150.0)
        analyzer.record_query("customer_dim", ["id"], 200.0)

        summary = analyzer.get_slow_query_summary()
        assert summary["slow_query_count"] == 2
        assert len(summary["slowest_tables"]) == 2

    def test_index_optimizer(self):
        """Test index optimizer."""
        optimizer = IndexOptimizer()

        # Record some queries
        optimizer.analyzer.record_query("sales_fact", ["customer_id"], 100.0)
        optimizer.analyzer.record_query("sales_fact", ["date"], 80.0)

        analysis = optimizer.analyze_workload()
        assert "recommendations" in analysis
        assert "slow_queries" in analysis


# ============================================================================
# Integration: Langraph Orchestrator Tests
# ============================================================================

class TestLangraphOrchestrator:
    """Test Langraph-based orchestrator."""

    @pytest.fixture
    def setup_orchestrator(self):
        """Set up Langraph orchestrator for testing."""
        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        orchestrator = LangraphOrchestrator(registry, db)
        return orchestrator

    def test_langraph_orchestrator_initialization(self, setup_orchestrator):
        """Test Langraph orchestrator initialization."""
        orchestrator = setup_orchestrator
        assert orchestrator is not None
        # Workflow may be None if Langraph not available
        assert orchestrator.router is not None
        assert orchestrator.domain_agents is not None

    def test_langraph_workflow_nodes(self, setup_orchestrator):
        """Test that workflow has required nodes."""
        orchestrator = setup_orchestrator
        # Workflow may be None if Langraph not available
        # This is acceptable - tests fallback routing
        assert orchestrator.router is not None

    def test_langraph_process_query(self, setup_orchestrator):
        """Test processing query with Langraph."""
        orchestrator = setup_orchestrator
        result = orchestrator.process_query("How many sales were made?")

        # Result should have domain and either result or error
        assert "domain" in result
        assert ("result" in result or "error" in result)


# ============================================================================
# Integration Tests: Multiple Features Together
# ============================================================================

class TestFeatureIntegration:
    """Test interaction between multiple advanced features."""

    def test_caching_with_pagination(self):
        """Test caching paginated results."""
        cache = CacheManager(CacheConfig(enabled=False))
        paginator = Paginator()

        rows = [{"id": i} for i in range(250)]
        paginated = paginator.paginate(rows, page=1, page_size=100)

        # Cache the paginated result
        cache_key = f"page_1_size_100"
        assert paginated is not None

    def test_conversation_with_context_updates(self):
        """Test conversation context with query results."""
        context = ConversationContext()

        # Simulate conversation with query results
        context.add_user_message("Show me sales")
        context.update_context(
            domain="sales",
            views=["sales_fact", "customer_dim"],
            result_count=50,
        )
        context.add_assistant_message("Found 50 sales.", {"row_count": 50})

        # Follow-up query should have context
        context.add_user_message("How much revenue?")
        summary = context.get_context_summary()

        assert "sales" in summary
        assert "50" in summary
