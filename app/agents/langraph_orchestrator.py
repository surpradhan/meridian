"""
LangGraph-based Multi-Agent Orchestrator

Provides a StateGraph workflow for multi-agent query coordination:

    route → process_agent → validate → execute → complete
                   ↓                       ↓
                 error                   error

The ``LangraphOrchestrator`` is wired as the primary execution engine
inside ``Orchestrator._init_langraph()``; a direct-agent fallback is used
when LangGraph is unavailable (see ``process_query()``).
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum

# First-party imports come before the optional third-party try/except so
# flake8 E402 is not triggered.
from app.views.registry import ViewRegistry
from app.database.connection import DbConnection
from app.query.builder import QueryBuilder
from app.query.validator import QueryValidator
from app.agents.router import RouterAgent
from app.agents.domain.sales import SalesAgent
from app.agents.domain.finance import FinanceAgent
from app.agents.domain.operations import OperationsAgent

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None  # type: ignore[assignment,misc]
    END = None  # type: ignore[assignment]

# Backward-compat alias — existing callers that import LANGRAPH_AVAILABLE still
# work.  Note: patching LANGGRAPH_AVAILABLE after import does NOT update this
# alias; patch both names if needed in tests.
LANGRAPH_AVAILABLE = LANGGRAPH_AVAILABLE

logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    """Lifecycle states in the LangGraph workflow."""
    INITIAL = "initial"
    ROUTING = "routing"
    AGENT_PROCESSING = "agent_processing"
    VALIDATION = "validation"
    EXECUTION = "execution"
    COMPLETE = "complete"
    ERROR = "error"


class GraphState(TypedDict, total=False):
    """Typed state dict that flows through the LangGraph StateGraph.

    ``total=False`` because the dict grows incrementally as nodes execute —
    only ``query`` is guaranteed to be present in the initial state.
    """
    # --- Input ---
    query: str
    domain: str                        # pre-routed domain (if set by caller)
    context_summary: Optional[str]     # conversation context injected by Orchestrator
    conversation_id: str

    # --- Set by _route_query ---
    routing_confidence: float

    # --- Set by _process_with_agent (mirrors domain-agent result dict) ---
    result: List[Dict[str, Any]]
    row_count: int
    sql: str
    views: List[str]
    confidence: float
    cache_hit: bool
    suggestions: List[str]
    interpretation_method: str

    # --- Set by _validate_query ---
    validation_passed: bool

    # --- Workflow metadata ---
    state: str       # WorkflowState value
    error: str       # error message; presence of this key signals failure


class LangraphOrchestrator:
    """
    LangGraph-based orchestrator for multi-agent query processing.

    Uses ``StateGraph[GraphState]`` for workflow management. The compiled
    graph is exposed as ``self.graph`` and is invoked by the outer
    ``Orchestrator`` as the primary execution path when LangGraph is
    available.
    """

    def __init__(
        self,
        registry: ViewRegistry,
        db: DbConnection,
        *,
        router: Optional[RouterAgent] = None,
        domain_agents: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialise the LangGraph orchestrator.

        Args:
            registry: ViewRegistry instance.
            db: Database connection instance.
            router: Pre-built RouterAgent to share with the outer Orchestrator
                (avoids double-instantiation and keeps mocks effective in tests).
                A new RouterAgent is created if not supplied.
            domain_agents: Pre-built domain-agent map to share with the outer
                Orchestrator.  A fresh set is created if not supplied.
        """
        self.registry = registry
        self.db = db
        self.builder = QueryBuilder(registry)
        self.validator = QueryValidator(registry)
        self.router = router or RouterAgent(registry)

        self.domain_agents: Dict[str, Any] = domain_agents or {
            "sales": SalesAgent(registry, db, self.builder),
            "finance": FinanceAgent(registry, db, self.builder),
            "operations": OperationsAgent(registry, db, self.builder),
        }

        self.workflow: Any = None
        self.graph: Any = None
        if LANGGRAPH_AVAILABLE:
            self.workflow = self._build_workflow()
            self.graph = self.workflow.compile()
            logger.debug("LangraphOrchestrator: LangGraph workflow compiled")
        else:
            logger.warning("LangGraph not available — LangraphOrchestrator in fallback mode")

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_workflow(self) -> Any:
        """Build the LangGraph StateGraph workflow."""
        workflow: Any = StateGraph(GraphState)

        workflow.add_node("route",         self._route_query)
        workflow.add_node("process_agent", self._process_with_agent)
        workflow.add_node("validate",      self._validate_query)
        workflow.add_node("execute",       self._execute_query)
        workflow.add_node("complete",      self._complete_query)
        workflow.add_node("error",         self._handle_error)

        workflow.set_entry_point("route")

        workflow.add_edge("route", "process_agent")
        # After process_agent: go to validate on success, error on failure.
        workflow.add_conditional_edges("process_agent", self._should_validate)
        workflow.add_edge("validate", "execute")
        # After execute: go to complete on success, error on failure.
        workflow.add_conditional_edges("execute", self._should_complete)
        workflow.add_edge("complete", END)
        workflow.add_edge("error",   END)

        return workflow

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    def _route_query(self, state: GraphState) -> GraphState:
        """Route query to the appropriate domain.

        If ``domain`` is already set in state (pre-routed by the outer
        ``Orchestrator``) the LLM routing call is skipped so we don't
        discard the caller's decision or waste an API call.
        """
        if state.get("domain"):
            state["state"] = WorkflowState.ROUTING.value
            return state

        query = state.get("query", "")
        domain, confidence = self.router.route(query)
        state["domain"] = domain
        state["routing_confidence"] = confidence
        state["state"] = WorkflowState.ROUTING.value
        logger.debug(f"LangGraph routed to {domain!r} (confidence {confidence:.2f})")
        return state

    def _process_with_agent(self, state: GraphState) -> GraphState:
        """Process the query with the appropriate domain agent.

        Threads ``context_summary`` from conversation state into the agent
        call so multi-turn references resolve correctly.
        """
        domain: Optional[str] = state.get("domain")
        query = state.get("query", "")
        context_summary: Optional[str] = state.get("context_summary")

        agent = self.domain_agents.get(domain or "")
        if not agent:
            state["error"] = f"Unknown domain: {domain!r}"
            return state

        try:
            result: Dict[str, Any] = agent.process_query(query, context_summary)
            state.update(result)  # type: ignore[typeddict-item]
            state["state"] = WorkflowState.AGENT_PROCESSING.value
        except Exception as exc:
            logger.error(f"LangGraph agent processing failed: {exc}")
            state["error"] = str(exc)

        return state

    def _should_validate(self, state: GraphState) -> str:
        """Conditional edge: route to 'validate' on success, 'error' on failure."""
        return "validate" if "error" not in state else "error"

    def _validate_query(self, state: GraphState) -> GraphState:
        """Validate that the agent produced a usable result.

        The domain agent runs its own internal validation before this node
        executes, so this is a lightweight structural gate: confirm that a
        SQL query was generated.
        """
        if not state.get("sql"):
            state["error"] = "Agent did not produce a SQL query"
        else:
            state["validation_passed"] = True

        state["state"] = WorkflowState.VALIDATION.value
        return state

    def _should_complete(self, state: GraphState) -> str:
        """Conditional edge: route to 'complete' on success, 'error' on failure."""
        return "complete" if "error" not in state else "error"

    def _execute_query(self, state: GraphState) -> GraphState:
        """State-advance node — SQL execution already happened in process_agent.

        ``agent.process_query()`` in ``_process_with_agent`` runs the full
        interpret → build-SQL → execute pipeline.  This node is intentionally
        a no-op: it marks the execution stage in the graph diagram and provides
        a hook for future instrumentation (caching, streaming, row-limit
        enforcement) without requiring graph topology changes.
        """
        state["state"] = WorkflowState.EXECUTION.value
        return state

    def _complete_query(self, state: GraphState) -> GraphState:
        """Mark the workflow as complete."""
        state["state"] = WorkflowState.COMPLETE.value
        logger.info("LangGraph query completed successfully")
        return state

    def _handle_error(self, state: GraphState) -> GraphState:
        """Log and mark the workflow as failed."""
        error = state.get("error", "Unknown error")
        logger.error(f"LangGraph query failed: {error}")
        state["state"] = WorkflowState.ERROR.value
        return state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a query through the LangGraph workflow (or fallback).

        Args:
            query: Natural language query string.

        Returns:
            Dict with result rows, SQL, domain, routing metadata, etc.
        """
        initial_state: GraphState = {
            "query": query,
            "state": WorkflowState.INITIAL.value,
        }

        try:
            if self.graph is not None:
                final_state = self.graph.invoke(initial_state)
                # Strip internal LangGraph bookkeeping keys.
                return {k: v for k, v in final_state.items() if not k.startswith("_")}

            # Fallback: direct dispatch without LangGraph.
            domain, confidence = self.router.route(query)
            agent = self.domain_agents.get(domain)
            if not agent:
                return {
                    "error": f"Unknown domain: {domain!r}",
                    "query": query,
                    "state": WorkflowState.ERROR.value,
                }
            result = agent.process_query(query)
            result["domain"] = domain
            result["routing_confidence"] = confidence
            result["state"] = WorkflowState.COMPLETE.value
            return result

        except Exception as exc:
            logger.error(f"LangGraph workflow execution failed: {exc}")
            return {
                "error": str(exc),
                "query": query,
                "state": WorkflowState.ERROR.value,
            }

    def get_workflow_graph(self) -> str:
        """Return a Mermaid diagram of the compiled workflow graph.

        Uses ``draw_mermaid()`` (no extra dependencies) rather than
        ``draw_ascii()`` which requires the optional *grandalf* package.
        """
        if self.graph is None:
            return "LangGraph not available"
        return self.graph.get_graph().draw_mermaid()
