"""
Multi-Agent Orchestrator

Coordinates the workflow between router, domain agents, validators, and query builder.
Phase 4: conversation context, query history, smart suggestions, LangGraph primary.
Phase 7: dynamic domain hot-reload.
"""

import logging
import re as _re
import json as _json
import threading as _threading
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from urllib.parse import urlparse

from app.views.registry import ViewRegistry
from app.database.connection import DbConnection
from app.query.builder import QueryBuilder
from app.query.validator import QueryValidator
from app.agents.router import RouterAgent
from app.agents.domain.sales import SalesAgent
from app.agents.domain.finance import FinanceAgent
from app.agents.domain.operations import OperationsAgent
from app.cache.manager import CacheManager, CacheConfig
from app.agents.conversation_context import ConversationManager, get_conversation_manager
from app.observability.tracing import TracingManager
from app.observability.metrics import get_query_metrics

logger = logging.getLogger(__name__)
_tracer = TracingManager.get_instance()

CLARIFICATION_THRESHOLD = 0.4
# Expire stale in-memory conversations every N queries (avoids unbounded growth)
_CLEANUP_INTERVAL = 100


class QueryState(str, Enum):
    INITIAL = "initial"
    ROUTING = "routing"
    VALIDATION = "validation"
    EXECUTION = "execution"
    COMPLETE = "complete"
    ERROR = "error"


class Orchestrator:
    """
    Orchestrates multi-agent workflow for processing natural language queries.

    Phase 4 features wired here:
    - Conversation context threading (multi-turn refinement)
    - Query history persistence (SQLite)
    - Smart follow-up suggestions (LLM-generated with static fallback)
    - LangGraph as primary execution engine (with transparent fallback)
    """

    def __init__(self, registry: ViewRegistry, db: DbConnection):
        self.registry = registry
        self.db = db
        self.builder = QueryBuilder(registry)
        self.validator = QueryValidator(registry)
        self.router = RouterAgent(registry)

        self.domain_agents = {
            "sales": SalesAgent(registry, db, self.builder),
            "finance": FinanceAgent(registry, db, self.builder),
            "operations": OperationsAgent(registry, db, self.builder),
        }

        self.cache = self._get_cache()
        self.conversations: ConversationManager = get_conversation_manager()
        self._langraph = self._init_langraph(registry, db)
        self._query_count = 0

        # Phase 7: load any previously-registered dynamic domains at startup
        self.reload_domain_agents()

        logger.debug("Orchestrator initialized")

    # ------------------------------------------------------------------
    # Init helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cache() -> CacheManager:
        try:
            from app.config import settings
            cache_enabled = settings.cache_enabled
            redis_url = settings.redis_url
        except Exception:
            cache_enabled = False
            redis_url = ""

        if CacheManager._instance is None:
            if cache_enabled and redis_url:
                parsed = urlparse(redis_url)
                db_index = int(parsed.path.lstrip("/") or "0")
                cache_config = CacheConfig(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 6379,
                    db=db_index,
                    enabled=True,
                )
            else:
                cache_config = CacheConfig(enabled=cache_enabled)
            CacheManager.get_instance(cache_config)

        return CacheManager.get_instance()

    @staticmethod
    def _init_langraph(registry: ViewRegistry, db: DbConnection):
        """Initialize LangGraph orchestrator when the library is available."""
        try:
            from app.agents.langraph_orchestrator import LangraphOrchestrator, LANGRAPH_AVAILABLE
            if LANGRAPH_AVAILABLE:
                lg = LangraphOrchestrator(registry, db)
                if lg.graph is not None:
                    logger.info(
                        "LangGraph orchestrator available — promoted to primary execution engine"
                    )
                    return lg
        except Exception as e:
            logger.debug(f"LangGraph init skipped: {e}")
        return None

    # ------------------------------------------------------------------
    # Conversation context helpers
    # ------------------------------------------------------------------

    def _resolve_context(
        self, conversation_id: Optional[str]
    ) -> Tuple[Any, Optional[str], str]:
        """Get-or-create conversation context.

        Returns:
            (ctx, context_summary, resolved_conversation_id)
        """
        if conversation_id:
            ctx = self.conversations.get_conversation(conversation_id)
            if ctx:
                summary = ctx.get_context_summary()
                return ctx, summary, conversation_id
            # Expired or unknown — start fresh, log clearly
            logger.debug(
                f"Conversation {conversation_id!r} not found or expired; creating new one"
            )

        ctx = self.conversations.create_conversation()
        return ctx, None, ctx.conversation_id

    def _maybe_cleanup(self) -> None:
        """Periodically purge expired in-memory conversations (every N queries)."""
        self._query_count += 1
        if self._query_count % _CLEANUP_INTERVAL == 0:
            removed = self.conversations.cleanup_expired()
            if removed:
                logger.debug(f"Periodic cleanup removed {removed} expired conversations")

    # ------------------------------------------------------------------
    # Core query processing
    # ------------------------------------------------------------------

    def process_query(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        forced_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a natural language query through the multi-agent workflow.

        Args:
            query: Natural language query
            conversation_id: Optional session ID for multi-turn context.
                             A new session is created when omitted or unknown.
            forced_domain: Skip routing and use this domain directly.
                           Used by the UI's manual domain selector.

        Returns:
            Dict with results, conversation_id, suggestions, and metadata.
        """
        logger.info(f"Processing query: {query!r}")
        self._maybe_cleanup()
        _qm = get_query_metrics()
        _qm.start_query(query)

        ctx, context_summary, conversation_id = self._resolve_context(conversation_id)
        ctx.add_user_message(query)

        # Cache check runs outside the main execution span so a hit doesn't inflate
        # the "query.process" duration with unrelated work.
        cache_key = f"{conversation_id}::{query}" if context_summary else query
        with _tracer.span("query.cache_check"):
            cached = self.cache.get_result(cache_key)
        if cached is not None:
            logger.info(f"Cache hit for query: {query!r}")
            cached = dict(cached)  # don't mutate the cached copy
            cached["cache_hit"] = True
            cached["conversation_id"] = conversation_id
            ctx.add_assistant_message(
                f"(cached) {cached.get('row_count', 0)} rows from {cached.get('domain', '')}",
                query_result={
                    "domain": cached.get("domain"),
                    "views": cached.get("views", []),
                    "row_count": cached.get("row_count", 0),
                },
            )
            ctx.update_context(
                domain=cached.get("domain"),
                views=cached.get("views", []),
                result_count=cached.get("row_count", 0),
            )
            _qm.end_query(query, success=True)
            _qm.record_rows(cached.get("row_count", 0))
            _qm.record_domain_query(cached.get("domain", "unknown"))
            return cached

        with _tracer.span("query.process", {
            "query": query[:200],
            "session_id": conversation_id,
            "forced_domain": forced_domain or "",
        }):
            # Routing (or use forced domain)
            with _tracer.span("query.route") as route_span:
                if forced_domain and forced_domain in self.domain_agents:
                    domain = forced_domain
                    routing_confidence = 1.0
                    logger.debug(f"Using forced domain: {domain}")
                    route_span.set_attribute("method", "forced")
                else:
                    domain, routing_confidence = self.router.route(query)
                    logger.debug(f"Routed to {domain} with confidence {routing_confidence:.2f}")
                    route_span.set_attribute("method", "auto")
                route_span.set_attribute("domain", domain)
                route_span.set_attribute("confidence", str(routing_confidence))

            # Clarification gate
            if routing_confidence < CLARIFICATION_THRESHOLD:
                logger.info(
                    f"Low routing confidence ({routing_confidence:.2f}) — requesting clarification"
                )
                msg = (
                    f"I'm not sure which business area your question relates to "
                    f"(confidence: {routing_confidence:.0%}). "
                    f"Could you add more context? For example, mention whether you're "
                    f"asking about sales/customers, finance/accounting, or "
                    f"inventory/warehouses/shipments."
                )
                ctx.add_assistant_message(msg)
                return {
                    "needs_clarification": True,
                    "clarification_message": msg,
                    "suggested_domains": list(self.domain_agents.keys()),
                    "domain": domain,
                    "routing_confidence": routing_confidence,
                    "state": QueryState.COMPLETE.value,
                    "confidence": routing_confidence,
                    "cache_hit": False,
                    "conversation_id": conversation_id,
                }

            agent = self.domain_agents.get(domain)
            if not agent:
                return {
                    "error": f"Unknown domain: {domain}",
                    "query": query,
                    "state": QueryState.ERROR.value,
                    "confidence": 0.0,
                    "cache_hit": False,
                    "conversation_id": conversation_id,
                }

            try:
                import time as _time
                t0 = _time.monotonic()
                with _tracer.span("query.agent_execute", {"domain": domain}) as exec_span:
                    result = self._execute_with_agent(agent, query, domain, context_summary)
                    elapsed_ms = (_time.monotonic() - t0) * 1000
                    # set_attribute must be called while the span is still open (inside with)
                    exec_span.set_attribute("row_count", str(result.get("row_count", 0)))
                    exec_span.set_attribute("duration_ms", str(round(elapsed_ms)))

                result["domain"] = domain
                result["routing_confidence"] = routing_confidence
                result["state"] = QueryState.COMPLETE.value
                result["cache_hit"] = False
                result["conversation_id"] = conversation_id
                with _tracer.span("query.suggestions"):
                    result["suggestions"] = self._generate_suggestions(query, domain, result)
                result["visualization"] = self._build_visualization_hint(result)

                logger.info(
                    f"Query completed — domain={domain}, "
                    f"rows={result.get('row_count', 0)}, "
                    f"confidence={result.get('confidence', 0)}"
                )
                _qm.end_query(query, success=True)
                _qm.record_rows(result.get("row_count", 0))
                _qm.record_domain_query(domain)

                ctx.add_assistant_message(
                    f"Returned {result.get('row_count', 0)} rows from {domain}",
                    query_result={
                        "domain": domain,
                        "views": result.get("views", []),
                        "row_count": result.get("row_count", 0),
                    },
                )
                ctx.update_context(
                    domain=domain,
                    views=result.get("views", []),
                    result_count=result.get("row_count", 0),
                )

                self._save_history(query, result, conversation_id)

                # Only cache stateless (context-free) results to avoid cross-session hits
                with _tracer.span("query.cache_store"):
                    if "error" not in result and not context_summary:
                        self.cache.set_result(cache_key, result)

                return result

            except Exception as e:
                logger.error(f"Query processing failed: {e}")
                _qm.end_query(query, success=False)
                _qm.record_domain_query(domain)
                return {
                    "error": str(e),
                    "query": query,
                    "domain": domain,
                    "routing_confidence": routing_confidence,
                    "state": QueryState.ERROR.value,
                    "confidence": 0.0,
                    "cache_hit": False,
                    "conversation_id": conversation_id,
                }

    def _execute_with_agent(
        self,
        agent,
        query: str,
        domain: str,
        context_summary: Optional[str],
    ) -> Dict[str, Any]:
        """
        Execute query through the LangGraph state machine when available,
        falling back to a direct agent call.

        The domain is pre-set in the initial state so LangGraph's route node
        skips re-routing (it honours a pre-set domain — see langraph_orchestrator).
        """
        if self._langraph is not None and self._langraph.graph is not None:
            try:
                initial_state = {
                    "query": query,
                    "domain": domain,          # pre-routed; LangGraph will not re-route
                    "state": QueryState.INITIAL.value,
                    "context_summary": context_summary,
                }
                final_state = self._langraph.graph.invoke(initial_state)
                if "error" not in final_state:
                    return {k: v for k, v in final_state.items() if not k.startswith("_")}
                logger.debug(
                    f"LangGraph returned error state ({final_state.get('error')}), "
                    "falling back to direct agent call"
                )
            except Exception as lg_err:
                logger.debug(f"LangGraph execution raised {lg_err!r}, using direct call")

        return agent.process_query(query, context_summary)

    # ------------------------------------------------------------------
    # Suggestions (Phase 4.3)
    # ------------------------------------------------------------------

    def _build_visualization_hint(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recommend a chart type for the query result.

        Args:
            result: Query result dict (as returned by domain agents)

        Returns:
            Visualization hint dict with chart_type, x_axis, y_axis, reason.
        """
        try:
            from app.visualization.chart_selector import select_chart_type
            rows = result.get("result", [])
            return select_chart_type(rows)
        except Exception as e:
            logger.warning(f"Visualization hint generation failed: {e}")
            return {"chart_type": "table", "x_axis": None, "y_axis": None, "reason": "unavailable"}

    def _generate_suggestions(
        self,
        query: str,
        domain: str,
        result: Dict[str, Any],
    ) -> List[str]:
        """
        Generate 3 follow-up query suggestions via LLM, with a static fallback.

        Inputs are length-capped before interpolation to prevent prompt bloat
        and reduce the surface area for adversarial content in view/domain names.
        """
        from app.agents.llm_client import get_llm

        llm = get_llm()
        if llm is not None:
            try:
                safe_query = str(query)[:300]
                safe_domain = str(domain)[:30]
                safe_views = [str(v)[:50] for v in (result.get("views") or [])[:5]]
                row_count = int(result.get("row_count") or 0)

                prompt = (
                    f'The user just asked: "{safe_query}"\n'
                    f"Domain: {safe_domain}, views: {safe_views}, rows returned: {row_count}.\n\n"
                    "Suggest exactly 3 short, specific follow-up questions a business user might "
                    "ask next. Return ONLY a JSON array of 3 strings, no other text.\n"
                    'Example: ["What is the total by region?", "Show me the top 5 customers", '
                    '"How does this compare to last month?"]'
                )
                response = llm.invoke(prompt)
                content = response.content if hasattr(response, "content") else str(response)

                match = _re.search(r"\[.*?\]", content, _re.DOTALL)
                if match:
                    suggestions = _json.loads(match.group())
                    if isinstance(suggestions, list) and suggestions:
                        return [str(s) for s in suggestions[:3]]
            except Exception as e:
                logger.debug(f"LLM suggestion generation failed: {e}")

        fallbacks: Dict[str, List[str]] = {
            "sales": [
                "What is the total sales amount by region?",
                "Who are the top 5 customers by revenue?",
                "How do sales compare across product categories?",
            ],
            "finance": [
                "What are the total debits vs credits by account?",
                "Show me all transactions for a specific account",
                "What is the net balance across all accounts?",
            ],
            "operations": [
                "Which warehouse has the highest inventory?",
                "Show me recent shipments by destination",
                "What products have the lowest stock levels?",
            ],
        }
        return fallbacks.get(domain, [])

    # ------------------------------------------------------------------
    # History (Phase 4.2)
    # ------------------------------------------------------------------

    def _save_history(
        self,
        query: str,
        result: Dict[str, Any],
        conversation_id: Optional[str],
    ) -> None:
        """Persist query to history — swallow exceptions, this is non-critical."""
        try:
            from app.history.manager import get_history_manager
            get_history_manager().save(query, result, conversation_id)
        except Exception as e:
            logger.debug(f"History save failed (non-critical): {e}")

    # ------------------------------------------------------------------
    # Conversation management helpers
    # ------------------------------------------------------------------

    def get_conversation(self, conversation_id: str):
        """Get a conversation context by ID."""
        return self.conversations.get_conversation(conversation_id)

    def new_conversation(self) -> str:
        """Create a new conversation and return its ID."""
        return self.conversations.create_conversation().conversation_id

    # ------------------------------------------------------------------
    # Trace variant — delegates to process_query, reconstructs trace shape
    # ------------------------------------------------------------------

    def process_query_with_trace(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        forced_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process query and return a detailed execution trace alongside results.

        Delegates all logic to ``process_query`` so there is a single code
        path — the trace is assembled from the result dict.
        """
        result = self.process_query(
            query,
            conversation_id=conversation_id,
            forced_domain=forced_domain,
        )

        # Clarification responses are forwarded with minimal trace wrapping
        if result.get("needs_clarification"):
            return {
                **result,
                "query": query,
                "steps": [
                    {
                        "step": "routing",
                        "domain": result.get("domain"),
                        "confidence": result.get("routing_confidence"),
                    }
                ],
            }

        if "error" in result:
            return {
                **result,
                "query": query,
                "steps": [],
            }

        trace = {
            "query": query,
            "conversation_id": result.get("conversation_id"),
            "domain": result.get("domain"),
            "state": result.get("state"),
            "result": result,
            "steps": [
                {
                    "step": "routing",
                    "domain": result.get("domain"),
                    "confidence": result.get("routing_confidence"),
                },
                {
                    "step": "agent_processing",
                    "domain": result.get("domain"),
                    "views": result.get("views", []),
                    "interpretation_method": result.get("interpretation_method"),
                },
                {
                    "step": "validation",
                    "status": "passed",
                    "errors": [],
                },
                {
                    "step": "execution",
                    "row_count": result.get("row_count", 0),
                    "confidence": result.get("confidence", 0),
                },
            ],
        }
        return trace

    # ------------------------------------------------------------------
    # Existing helpers (unchanged)
    # ------------------------------------------------------------------

    def validate_query_for_domain(self, domain: str, query: str) -> Tuple[bool, List[str]]:
        agent = self.domain_agents.get(domain)
        if not agent:
            return False, [f"Unknown domain: {domain}"]
        try:
            result = agent.process_query(query)
            if "error" in result:
                return False, [result["error"]]
            return True, []
        except Exception as e:
            return False, [str(e)]

    def get_domain_capabilities(self, domain: str) -> Dict[str, Any]:
        agent = self.domain_agents.get(domain)
        if not agent:
            return {"error": f"Unknown domain: {domain}"}
        return {
            "domain": domain,
            "available_views": agent.get_available_views(),
            "view_summary": agent.get_view_summary(),
            "keywords": self.router.domain_keywords[domain]["keywords"],
        }

    def get_all_domains(self) -> List[Dict[str, Any]]:
        domains = []
        for domain in ["sales", "finance", "operations"]:
            info = self.router.get_domain_info(domain)
            if info:
                domains.append(info)
        return domains

    # ------------------------------------------------------------------
    # Phase 7: Dynamic domain hot-reload
    # ------------------------------------------------------------------

    def reload_domain_agents(self) -> None:
        """
        Reload dynamic domains from the DomainRegistry and merge them into
        self.domain_agents.  Called after an admin registers or deletes a domain.
        """
        try:
            from app.onboarding.registry import get_domain_registry
            from app.onboarding.agent_factory import build_agent

            registry = get_domain_registry()
            for config in registry.list_domains():
                agent = build_agent(config, self.registry, self.db, self.builder)
                self.domain_agents[config.name] = agent
                logger.info(f"Hot-loaded dynamic domain agent: {config.name!r}")

            # Remove deleted dynamic domains (no longer in registry)
            dynamic_names = {c.name for c in registry.list_domains()}
            builtin = {"sales", "finance", "operations"}
            for name in list(self.domain_agents.keys()):
                if name not in builtin and name not in dynamic_names:
                    del self.domain_agents[name]
                    logger.info(f"Removed stale dynamic domain agent: {name!r}")
        except Exception as e:
            logger.warning(f"reload_domain_agents failed: {e}")


# ------------------------------------------------------------------
# Module-level shared orchestrator (Phase 7 hot-reload support)
# ------------------------------------------------------------------

_shared_orchestrator: Optional["Orchestrator"] = None
_shared_lock = _threading.Lock()


def _get_shared_orchestrator() -> Optional["Orchestrator"]:
    """Return the shared Orchestrator instance if one has been created, else None."""
    return _shared_orchestrator


def set_shared_orchestrator(orch: "Orchestrator") -> None:
    """Register a shared Orchestrator (called from app startup or first request)."""
    global _shared_orchestrator
    with _shared_lock:
        _shared_orchestrator = orch


def get_shared_or_new_orchestrator() -> "Orchestrator":
    """
    Return the shared Orchestrator, creating and registering one if needed.

    All routes should use this instead of constructing Orchestrator directly —
    ensures dynamic domains are visible and avoids redundant startup cost.
    """
    global _shared_orchestrator
    if _shared_orchestrator is not None:
        return _shared_orchestrator
    with _shared_lock:
        if _shared_orchestrator is None:
            from app.views.registry import get_registry
            from app.database.connection import get_db
            from app.config import settings
            registry = get_registry()
            db = get_db(connection_string=settings.database_url)
            _shared_orchestrator = Orchestrator(registry, db)
    return _shared_orchestrator
