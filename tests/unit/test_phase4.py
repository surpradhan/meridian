"""
Unit Tests for Phase 4: Conversational Intelligence

Covers:
- ConversationContext / ConversationManager (4.1)
- HistoryManager (4.2)
- Orchestrator conversation threading and suggestions (4.1, 4.3)
- LangGraph promotion (4.4)
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# 4.1 ConversationContext
# ---------------------------------------------------------------------------

class TestConversationContext:

    def test_create_conversation(self):
        from app.agents.conversation_context import ConversationManager
        mgr = ConversationManager()
        ctx = mgr.create_conversation()
        assert ctx.conversation_id
        assert len(ctx.messages) == 0

    def test_add_user_and_assistant_messages(self):
        from app.agents.conversation_context import ConversationContext
        ctx = ConversationContext()
        ctx.add_user_message("How many sales?")
        ctx.add_assistant_message("Found 42 rows.", query_result={"row_count": 42})
        assert len(ctx.messages) == 2
        assert ctx.messages[0].role == "user"
        assert ctx.messages[1].role == "assistant"

    def test_context_summary_includes_domain(self):
        from app.agents.conversation_context import ConversationContext
        ctx = ConversationContext()
        ctx.add_user_message("How many sales?")
        ctx.update_context(domain="sales", views=["sales_fact"], result_count=10)
        summary = ctx.get_context_summary()
        assert "sales" in summary.lower()

    def test_get_message_history_limit(self):
        from app.agents.conversation_context import ConversationContext
        ctx = ConversationContext()
        for i in range(10):
            ctx.add_user_message(f"Question {i}")
        history = ctx.get_message_history(limit=3)
        assert len(history) == 3

    def test_expired_conversation_removed(self):
        from app.agents.conversation_context import ConversationManager, ConversationContext
        from datetime import datetime, timedelta

        mgr = ConversationManager()
        ctx = mgr.create_conversation()
        # Force the created_at timestamp to the past
        ctx.created_at = datetime.utcnow() - timedelta(minutes=120)

        retrieved = mgr.get_conversation(ctx.conversation_id)
        assert retrieved is None

    def test_session_variables(self):
        from app.agents.conversation_context import ConversationContext
        ctx = ConversationContext()
        ctx.set_session_variable("last_region", "WEST")
        assert ctx.get_session_variable("last_region") == "WEST"
        assert ctx.get_session_variable("nonexistent") is None

    def test_cleanup_expired(self):
        from app.agents.conversation_context import ConversationManager
        from datetime import datetime, timedelta

        mgr = ConversationManager()
        ctx1 = mgr.create_conversation()
        ctx2 = mgr.create_conversation()
        # Expire ctx1
        ctx1.created_at = datetime.utcnow() - timedelta(minutes=120)

        removed = mgr.cleanup_expired()
        assert removed == 1
        assert mgr.get_conversation(ctx2.conversation_id) is not None

    def test_get_conversation_manager_singleton(self):
        from app.agents.conversation_context import get_conversation_manager
        mgr1 = get_conversation_manager()
        mgr2 = get_conversation_manager()
        assert mgr1 is mgr2

    def test_conversation_to_dict(self):
        from app.agents.conversation_context import ConversationContext
        ctx = ConversationContext()
        ctx.add_user_message("hello")
        d = ctx.to_dict()
        assert "conversation_id" in d
        assert d["message_count"] == 1
        assert "messages" in d

    def test_manager_stats(self):
        from app.agents.conversation_context import ConversationManager
        mgr = ConversationManager()
        mgr.create_conversation()
        stats = mgr.get_stats()
        assert "active_conversations" in stats
        assert stats["active_conversations"] >= 1


# ---------------------------------------------------------------------------
# 4.2 HistoryManager
# ---------------------------------------------------------------------------

class TestHistoryManager:

    @pytest.fixture
    def history_manager(self, tmp_path):
        from app.history.manager import HistoryManager
        db_file = str(tmp_path / "test_history.db")
        return HistoryManager(db_path=db_file)

    def test_save_and_list(self, history_manager):
        result = {
            "domain": "sales",
            "sql": "SELECT * FROM sales_fact",
            "row_count": 5,
            "confidence": 0.85,
        }
        hid = history_manager.save("How many sales?", result)
        assert hid

        entries = history_manager.list()
        assert len(entries) == 1
        assert entries[0]["question"] == "How many sales?"
        assert entries[0]["domain"] == "sales"

    def test_get_by_id(self, history_manager):
        result = {"domain": "finance", "row_count": 3, "confidence": 0.9}
        hid = history_manager.save("Show ledger", result)
        entry = history_manager.get(hid)
        assert entry is not None
        assert entry["id"] == hid

    def test_get_nonexistent(self, history_manager):
        assert history_manager.get("nonexistent-uuid") is None

    def test_delete(self, history_manager):
        result = {"domain": "operations", "row_count": 10}
        hid = history_manager.save("Show inventory", result)
        deleted = history_manager.delete(hid)
        assert deleted
        assert history_manager.get(hid) is None

    def test_delete_nonexistent(self, history_manager):
        assert not history_manager.delete("nonexistent-uuid")

    def test_list_limit(self, history_manager):
        result = {"domain": "sales", "row_count": 1}
        for i in range(5):
            history_manager.save(f"Query {i}", result)
        entries = history_manager.list(limit=3)
        assert len(entries) == 3

    def test_list_newest_first(self, history_manager):
        result = {"domain": "sales", "row_count": 0}
        history_manager.save("First query", result)
        history_manager.save("Second query", result)
        entries = history_manager.list()
        assert entries[0]["question"] == "Second query"

    def test_save_with_conversation_id(self, history_manager):
        result = {"domain": "sales", "row_count": 5}
        hid = history_manager.save("Sales by region", result, conversation_id="conv-abc-123")
        entry = history_manager.get(hid)
        assert entry["conversation_id"] == "conv-abc-123"

    def test_save_with_error(self, history_manager):
        result = {"domain": "sales", "error": "View not found", "row_count": 0}
        hid = history_manager.save("Bad query", result)
        entry = history_manager.get(hid)
        assert entry["error"] == "View not found"


# ---------------------------------------------------------------------------
# 4.1 / 4.3  Orchestrator conversation + suggestions
# ---------------------------------------------------------------------------

class TestOrchestratorPhase4:

    @pytest.fixture
    def orchestrator(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        return Orchestrator(registry, db)

    def test_process_query_returns_conversation_id(self, orchestrator):
        result = orchestrator.process_query("How many sales?")
        assert "conversation_id" in result
        assert result["conversation_id"]

    def test_conversation_id_persists_across_turns(self, orchestrator):
        result1 = orchestrator.process_query("How many sales?")
        conv_id = result1["conversation_id"]

        result2 = orchestrator.process_query("Break that down by region", conversation_id=conv_id)
        assert result2["conversation_id"] == conv_id

    def test_unknown_conversation_id_creates_new(self, orchestrator):
        result = orchestrator.process_query("Show me sales", conversation_id="nonexistent-id")
        assert "conversation_id" in result
        assert result["conversation_id"] != "nonexistent-id"

    def test_suggestions_returned(self, orchestrator):
        result = orchestrator.process_query("How many sales?")
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)

    def test_suggestions_are_strings(self, orchestrator):
        result = orchestrator.process_query("What is the inventory?")
        for s in result["suggestions"]:
            assert isinstance(s, str)

    def test_suggestions_max_three(self, orchestrator):
        result = orchestrator.process_query("Show ledger transactions")
        assert len(result["suggestions"]) <= 3

    def test_new_conversation_helper(self, orchestrator):
        conv_id = orchestrator.new_conversation()
        assert conv_id
        ctx = orchestrator.get_conversation(conv_id)
        assert ctx is not None

    def test_get_nonexistent_conversation(self, orchestrator):
        assert orchestrator.get_conversation("nonexistent") is None

    def test_clarification_includes_conversation_id(self, orchestrator):
        # Patch router to return very low confidence
        with patch.object(orchestrator.router, "route", return_value=("sales", 0.1)):
            result = orchestrator.process_query("??!!")
        assert result.get("needs_clarification")
        assert "conversation_id" in result


# ---------------------------------------------------------------------------
# 4.4  LangGraph promotion
# ---------------------------------------------------------------------------

class TestLangGraphPromotion:

    def test_langraph_init_attempted(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        orch = Orchestrator(registry, db)
        # _langraph is either a LangraphOrchestrator or None — both are valid
        # depending on whether langraph is installed.
        assert hasattr(orch, "_langraph")

    def test_langraph_fallback_when_unavailable(self):
        """Orchestrator processes queries even when LangGraph is absent."""
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)

        orch = Orchestrator(registry, db)
        # Force-disable LangGraph to test fallback
        orch._langraph = None

        result = orch.process_query("Show me all sales")
        assert "domain" in result
        assert result.get("state") in ("complete", "error")


# ---------------------------------------------------------------------------
# Domain agent context_summary pass-through
# ---------------------------------------------------------------------------

class TestAgentContextPassthrough:

    @pytest.fixture
    def sales_agent(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection
        from app.query.builder import QueryBuilder
        from app.agents.domain.sales import SalesAgent

        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        builder = QueryBuilder(registry)
        return SalesAgent(registry, db, builder)

    def test_process_query_accepts_context_summary(self, sales_agent):
        result = sales_agent.process_query(
            "How many sales?",
            context_summary="Last domain queried: sales | Recent views: sales_fact",
        )
        assert "confidence" in result

    def test_llm_interpret_includes_context(self):
        from app.agents.domain.base_domain import _build_interpret_prompt
        prompt = _build_interpret_prompt(
            domain="sales",
            schema_json="{}",
            query="Show me the same data",
            context_summary="Last domain queried: sales | Last query returned 10 rows",
        )
        assert "conversation context" in prompt.lower()
        assert "Last domain queried" in prompt

    def test_llm_interpret_without_context_no_section(self):
        from app.agents.domain.base_domain import _build_interpret_prompt
        prompt = _build_interpret_prompt(
            domain="sales",
            schema_json="{}",
            query="How many sales?",
            context_summary=None,
        )
        assert "conversation context" not in prompt.lower()


# ---------------------------------------------------------------------------
# process_query_with_trace — conversation context threading
# ---------------------------------------------------------------------------

class TestProcessQueryWithTrace:

    @pytest.fixture
    def orchestrator(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        return Orchestrator(registry, db)

    def test_trace_has_required_steps(self, orchestrator):
        trace = orchestrator.process_query_with_trace("How many sales?")
        assert "steps" in trace
        step_names = [s["step"] for s in trace["steps"]]
        assert "routing" in step_names
        assert "agent_processing" in step_names

    def test_trace_includes_conversation_id(self, orchestrator):
        trace = orchestrator.process_query_with_trace("Show me sales data")
        assert "conversation_id" in trace or "conversation_id" in trace.get("result", {})

    def test_trace_threads_conversation_id(self, orchestrator):
        """Second trace call with the same conv_id should reuse the session."""
        trace1 = orchestrator.process_query_with_trace("How many sales?")
        # grab conv_id from either the top-level or nested result
        conv_id = trace1.get("conversation_id") or trace1.get("result", {}).get("conversation_id")
        assert conv_id

        trace2 = orchestrator.process_query_with_trace(
            "Break that down by region", conversation_id=conv_id
        )
        conv_id2 = trace2.get("conversation_id") or trace2.get("result", {}).get("conversation_id")
        assert conv_id2 == conv_id

    def test_trace_error_path_has_empty_steps(self, orchestrator):
        """An error result wraps into a trace with an empty steps list."""
        with patch.object(
            orchestrator.domain_agents["sales"],
            "process_query",
            side_effect=RuntimeError("boom"),
        ):
            with patch.object(orchestrator.router, "route", return_value=("sales", 0.9)):
                trace = orchestrator.process_query_with_trace("Show all sales")
        assert "steps" in trace
        assert trace["steps"] == []

    def test_trace_clarification_path_has_routing_step(self, orchestrator):
        with patch.object(orchestrator.router, "route", return_value=("sales", 0.1)):
            trace = orchestrator.process_query_with_trace("??")
        assert trace.get("needs_clarification")
        assert any(s["step"] == "routing" for s in trace.get("steps", []))


# ---------------------------------------------------------------------------
# Forced-domain threads context through orchestrator
# ---------------------------------------------------------------------------

class TestForcedDomain:

    @pytest.fixture
    def orchestrator(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        return Orchestrator(registry, db)

    def test_forced_domain_returns_correct_domain(self, orchestrator):
        result = orchestrator.process_query("Show all data", forced_domain="sales")
        assert result.get("domain") == "sales"

    def test_forced_domain_still_returns_conversation_id(self, orchestrator):
        result = orchestrator.process_query("Show all data", forced_domain="sales")
        assert "conversation_id" in result
        assert result["conversation_id"]

    def test_forced_domain_updates_conversation_state(self, orchestrator):
        result = orchestrator.process_query("Show all data", forced_domain="sales")
        conv_id = result["conversation_id"]
        ctx = orchestrator.get_conversation(conv_id)
        assert ctx is not None
        assert ctx.context["last_domain"] == "sales"

    def test_forced_domain_returns_suggestions(self, orchestrator):
        result = orchestrator.process_query("Show all data", forced_domain="finance")
        assert isinstance(result.get("suggestions"), list)

    def test_forced_domain_confidence_is_one(self, orchestrator):
        result = orchestrator.process_query("Show all data", forced_domain="operations")
        assert result.get("routing_confidence") == 1.0


# ---------------------------------------------------------------------------
# Cache-hit updates conversation state
# ---------------------------------------------------------------------------

class TestCacheHitConversationUpdate:

    @pytest.fixture
    def orchestrator(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        return Orchestrator(registry, db)

    def test_cache_hit_updates_conversation_context(self, orchestrator):
        cached_payload = {
            "domain": "sales",
            "views": ["sales_fact"],
            "row_count": 7,
            "confidence": 0.9,
            "suggestions": ["Follow-up?"],
        }
        with patch.object(orchestrator.cache, "get_result", return_value=cached_payload):
            result = orchestrator.process_query("How many sales?")

        assert result["cache_hit"] is True
        conv_id = result["conversation_id"]
        ctx = orchestrator.get_conversation(conv_id)
        assert ctx is not None
        assert ctx.context["last_domain"] == "sales"
        assert ctx.context["last_result_count"] == 7

    def test_cache_hit_carries_conversation_id(self, orchestrator):
        conv_id = orchestrator.new_conversation()
        cached_payload = {
            "domain": "finance",
            "views": [],
            "row_count": 3,
            "confidence": 0.8,
        }
        with patch.object(orchestrator.cache, "get_result", return_value=cached_payload):
            result = orchestrator.process_query("Show ledger", conversation_id=conv_id)

        assert result["conversation_id"] == conv_id


# ---------------------------------------------------------------------------
# LangGraph graph.invoke() is actually called (mock-based)
# ---------------------------------------------------------------------------

class TestLangGraphInvokeActuallyCalled:

    @pytest.fixture
    def orchestrator_with_mock_langraph(self):
        from app.views.registry import create_test_registry
        from app.database.connection import DbConnection, reset_db
        from app.agents.orchestrator import Orchestrator

        reset_db()
        registry = create_test_registry()
        db = DbConnection(is_mock=True)
        orch = Orchestrator(registry, db)
        return orch

    def test_graph_invoke_called_when_langraph_present(self, orchestrator_with_mock_langraph):
        orch = orchestrator_with_mock_langraph
        fake_result = {
            "domain": "sales",
            "views": ["sales_fact"],
            "row_count": 5,
            "confidence": 0.9,
            "sql": "SELECT 1",
            "state": "complete",
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = fake_result

        mock_langraph = MagicMock()
        mock_langraph.graph = mock_graph
        orch._langraph = mock_langraph

        orch.process_query("How many sales?")
        mock_graph.invoke.assert_called_once()

    def test_graph_invoke_receives_pre_routed_domain(self, orchestrator_with_mock_langraph):
        orch = orchestrator_with_mock_langraph
        fake_result = {
            "domain": "finance",
            "views": [],
            "row_count": 0,
            "confidence": 0.8,
            "state": "complete",
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = fake_result

        mock_langraph = MagicMock()
        mock_langraph.graph = mock_graph
        orch._langraph = mock_langraph

        with patch.object(orch.router, "route", return_value=("finance", 0.95)):
            orch.process_query("Show ledger")

        call_args = mock_graph.invoke.call_args[0][0]
        assert call_args["domain"] == "finance"

    def test_fallback_to_direct_when_invoke_errors(self, orchestrator_with_mock_langraph):
        orch = orchestrator_with_mock_langraph
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("graph exploded")

        mock_langraph = MagicMock()
        mock_langraph.graph = mock_graph
        orch._langraph = mock_langraph

        # Should not raise — should fall back to direct agent call
        result = orch.process_query("How many sales?")
        assert "domain" in result


# ---------------------------------------------------------------------------
# ConversationManager thread-safety / concurrency
# ---------------------------------------------------------------------------

class TestConversationManagerConcurrency:

    def test_concurrent_creates_all_succeed(self):
        import threading
        from app.agents.conversation_context import ConversationManager

        mgr = ConversationManager()
        created_ids: list = []
        errors: list = []
        lock = threading.Lock()

        def create_and_record():
            try:
                ctx = mgr.create_conversation()
                with lock:
                    created_ids.append(ctx.conversation_id)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=create_and_record) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent creates: {errors}"
        assert len(created_ids) == 20
        # All IDs must be unique
        assert len(set(created_ids)) == 20

    def test_concurrent_reads_and_writes(self):
        import threading
        from app.agents.conversation_context import ConversationManager

        mgr = ConversationManager()
        ctx = mgr.create_conversation()
        conv_id = ctx.conversation_id
        errors: list = []
        lock = threading.Lock()

        def read_and_write():
            try:
                for _ in range(5):
                    c = mgr.get_conversation(conv_id)
                    if c:
                        c.add_user_message("concurrent message")
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=read_and_write) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent reads/writes: {errors}"
