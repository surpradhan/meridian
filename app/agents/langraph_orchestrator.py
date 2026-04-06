"""
Langraph-based Multi-Agent Orchestrator

Replaces the state machine pattern with Langraph's workflow engine
for more robust, scalable multi-agent coordination.
"""

import logging
from typing import Dict, Any, List, Optional  # noqa: F401 — Optional used in _process_with_agent
from enum import Enum

try:
    from langraph.graph import StateGraph, END
    LANGRAPH_AVAILABLE = True
except ImportError:
    LANGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from app.views.registry import ViewRegistry
from app.database.connection import DbConnection
from app.query.builder import QueryBuilder
from app.query.validator import QueryValidator
from app.agents.router import RouterAgent
from app.agents.domain.sales import SalesAgent
from app.agents.domain.finance import FinanceAgent
from app.agents.domain.operations import OperationsAgent

logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    """States in Langraph workflow."""
    INITIAL = "initial"
    ROUTING = "routing"
    AGENT_PROCESSING = "agent_processing"
    VALIDATION = "validation"
    EXECUTION = "execution"
    COMPLETE = "complete"
    ERROR = "error"


class LangraphOrchestrator:
    """
    Langraph-based orchestrator for multi-agent query processing.

    Uses StateGraph for managing workflow states and transitions,
    with better support for conditional routing and error handling.
    """

    def __init__(
        self,
        registry: ViewRegistry,
        db: DbConnection,
    ):
        """Initialize Langraph orchestrator.

        Args:
            registry: ViewRegistry instance
            db: Database connection instance
        """
        self.registry = registry
        self.db = db
        self.builder = QueryBuilder(registry)
        self.validator = QueryValidator(registry)
        self.router = RouterAgent(registry)

        # Initialize domain agents
        self.domain_agents = {
            "sales": SalesAgent(registry, db, self.builder),
            "finance": FinanceAgent(registry, db, self.builder),
            "operations": OperationsAgent(registry, db, self.builder),
        }

        # Build Langraph workflow if available
        self.workflow = None
        self.graph = None
        if LANGRAPH_AVAILABLE:
            self.workflow = self._build_workflow()
            self.graph = self.workflow.compile()
            logger.debug("LangraphOrchestrator initialized with Langraph workflow")
        else:
            logger.warning("Langraph not available - using simplified workflow")

    def _build_workflow(self):
        """Build the Langraph StateGraph workflow.

        Returns:
            Compiled StateGraph
        """
        workflow = StateGraph(dict)

        # Add nodes for each workflow step
        workflow.add_node("route", self._route_query)
        workflow.add_node("process_agent", self._process_with_agent)
        workflow.add_node("validate", self._validate_query)
        workflow.add_node("execute", self._execute_query)
        workflow.add_node("complete", self._complete_query)
        workflow.add_node("error", self._handle_error)

        # Set entry point
        workflow.set_entry_point("route")

        # Add edges with conditional routing
        workflow.add_edge("route", "process_agent")
        workflow.add_conditional_edges(
            "process_agent",
            self._should_validate,
            {
                True: "validate",
                False: "error",
            }
        )
        workflow.add_edge("validate", "execute")
        workflow.add_conditional_edges(
            "execute",
            self._should_complete,
            {
                True: "complete",
                False: "error",
            }
        )
        workflow.add_edge("complete", END)
        workflow.add_edge("error", END)

        return workflow

    def _route_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Route query to appropriate domain.

        If ``domain`` is already set in state (pre-routed by the outer
        Orchestrator) routing is skipped so we don't discard the caller's
        domain choice or waste an LLM call.
        """
        if state.get("domain"):
            # Domain was pre-set by the caller — honour it.
            state["state"] = WorkflowState.ROUTING.value
            return state

        query = state.get("query", "")
        logger.debug(f"Routing query: {query}")

        domain, confidence = self.router.route(query)
        state["domain"] = domain
        state["routing_confidence"] = confidence
        state["state"] = WorkflowState.ROUTING.value

        logger.debug(f"Routed to {domain} with confidence {confidence:.2f}")
        return state

    def _process_with_agent(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process query with domain agent, threading conversation context."""
        domain = state.get("domain")
        query = state.get("query", "")
        context_summary: Optional[str] = state.get("context_summary")

        logger.debug(f"Processing with {domain} agent")

        agent = self.domain_agents.get(domain)
        if not agent:
            state["error"] = f"Unknown domain: {domain}"
            return state

        try:
            result = agent.process_query(query, context_summary)
            state.update(result)
            state["state"] = WorkflowState.AGENT_PROCESSING.value
            return state
        except Exception as e:
            logger.error(f"Agent processing failed: {e}")
            state["error"] = str(e)
            return state

    def _should_validate(self, state: Dict[str, Any]) -> bool:
        """Check if validation should proceed."""
        return "error" not in state

    def _validate_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate query structure."""
        views = state.get("views", [])
        filters = state.get("filters", {})
        aggregations = state.get("aggregations", {})

        logger.debug("Validating query")

        try:
            is_valid, errors = self.validator.validate(
                views=views,
                filters=filters,
                aggregations=aggregations,
            )

            if not is_valid:
                state["error"] = errors
                logger.warning(f"Validation errors: {errors}")
            else:
                state["validation_passed"] = True

            state["state"] = WorkflowState.VALIDATION.value
            return state

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            state["error"] = str(e)
            return state

    def _should_complete(self, state: Dict[str, Any]) -> bool:
        """Check if execution was successful."""
        return "error" not in state

    def _execute_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the query."""
        logger.debug("Executing query")
        state["state"] = WorkflowState.EXECUTION.value
        # Results are populated by domain agent already
        return state

    def _complete_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Mark query as complete."""
        logger.info("Query completed successfully")
        state["state"] = WorkflowState.COMPLETE.value
        return state

    def _handle_error(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Handle query execution error."""
        error = state.get("error", "Unknown error")
        logger.error(f"Query failed: {error}")
        state["state"] = WorkflowState.ERROR.value
        return state

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process query through Langraph workflow.

        Args:
            query: Natural language query

        Returns:
            Dict with results and metadata
        """
        logger.info(f"Processing query: {query}")

        initial_state = {
            "query": query,
            "state": WorkflowState.INITIAL.value,
        }

        try:
            # Use Langraph if available, otherwise use manual routing
            if self.graph is not None:
                final_state = self.graph.invoke(initial_state)
                response = {k: v for k, v in final_state.items()
                           if not k.startswith("_")}
            else:
                # Fallback to manual routing without Langraph
                domain, confidence = self.router.route(query)
                agent = self.domain_agents.get(domain)
                if not agent:
                    return {
                        "error": f"Unknown domain: {domain}",
                        "query": query,
                        "state": WorkflowState.ERROR.value,
                    }
                result = agent.process_query(query)
                result["domain"] = domain
                result["routing_confidence"] = confidence
                result["state"] = WorkflowState.COMPLETE.value
                response = result

            return response

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {
                "error": str(e),
                "query": query,
                "state": WorkflowState.ERROR.value,
            }

    def get_workflow_graph(self) -> str:
        """Get ASCII representation of workflow graph.

        Returns:
            ASCII diagram of the workflow
        """
        return self.graph.get_graph().draw_ascii()
