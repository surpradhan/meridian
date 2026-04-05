"""
Multi-Agent Orchestrator

Coordinates the workflow between router, domain agents, validators, and query builder.
Implements a state machine using Langraph for managing query processing across domains.
"""

import logging
from typing import Dict, Any, List, Tuple
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

logger = logging.getLogger(__name__)


class QueryState(str, Enum):
    """States in query processing workflow."""
    INITIAL = "initial"
    ROUTING = "routing"
    VALIDATION = "validation"
    EXECUTION = "execution"
    COMPLETE = "complete"
    ERROR = "error"


class Orchestrator:
    """
    Orchestrates multi-agent workflow for processing natural language queries.

    Workflow:
    1. Route query to appropriate domain agent (sales, finance, operations)
    2. Domain agent identifies views, filters, aggregations
    3. QueryValidator validates the query structure
    4. QueryBuilder generates SQL
    5. QueryExecutor runs the query
    6. Return results

    This implementation uses a state machine pattern to manage the workflow.
    """

    def __init__(
        self,
        registry: ViewRegistry,
        db: DbConnection,
    ):
        """
        Initialize the orchestrator.

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

        # Initialize cache (singleton — one Redis connection for the process)
        self.cache = self._get_cache()

        logger.debug("Orchestrator initialized")

    @staticmethod
    def _get_cache() -> CacheManager:
        """Get or initialize the process-wide CacheManager singleton."""
        try:
            from app.config import settings
            cache_enabled = settings.cache_enabled
            redis_url = settings.redis_url
        except Exception:
            cache_enabled = False
            redis_url = ""

        # get_instance only creates a new instance on the very first call;
        # subsequent calls return the existing one regardless of config arg.
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

    def process_query(self, query: str) -> Dict[str, Any]:
        """
        Process a natural language query through the multi-agent workflow.

        Args:
            query: Natural language query

        Returns:
            Dict with results, confidence, domain, and execution details
        """
        logger.info(f"Processing query: {query}")

        # Check cache before running full pipeline
        cached = self.cache.get_result(query)
        if cached is not None:
            logger.info(f"Cache hit for query: {query!r}")
            cached["cache_hit"] = True
            return cached

        # Step 1: Route query to appropriate domain
        domain, routing_confidence = self.router.route(query)
        logger.debug(f"Routed to {domain} with confidence {routing_confidence:.2f}")

        # Step 2: Get appropriate domain agent
        agent = self.domain_agents.get(domain)
        if not agent:
            return {
                "error": f"Unknown domain: {domain}",
                "query": query,
                "state": QueryState.ERROR.value,
                "confidence": 0.0,
                "cache_hit": False,
            }

        # Step 3: Process with domain agent
        try:
            result = agent.process_query(query)

            # Add orchestrator metadata
            result["domain"] = domain
            result["routing_confidence"] = routing_confidence
            result["state"] = QueryState.COMPLETE.value
            result["cache_hit"] = False

            logger.info(
                f"Query completed for domain {domain}. "
                f"Rows: {result.get('row_count', 0)}, Confidence: {result.get('confidence', 0)}"
            )

            # Cache successful results
            if "error" not in result:
                self.cache.set_result(query, result)

            return result

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return {
                "error": str(e),
                "query": query,
                "domain": domain,
                "routing_confidence": routing_confidence,
                "state": QueryState.ERROR.value,
                "confidence": 0.0,
                "cache_hit": False,
            }

    def validate_query_for_domain(self, domain: str, query: str) -> Tuple[bool, List[str]]:
        """
        Validate a query for a specific domain.

        Args:
            domain: Domain name (sales, finance, operations)
            query: Natural language query

        Returns:
            Tuple of (is_valid, error_messages)
        """
        agent = self.domain_agents.get(domain)
        if not agent:
            return False, [f"Unknown domain: {domain}"]

        try:
            # Let agent interpret the query
            result = agent.process_query(query)

            # Check if error occurred
            if "error" in result:
                return False, [result["error"]]

            return True, []

        except Exception as e:
            return False, [str(e)]

    def get_domain_capabilities(self, domain: str) -> Dict[str, Any]:
        """
        Get what a domain agent can do.

        Args:
            domain: Domain name

        Returns:
            Dict with domain capabilities
        """
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
        """
        Get information about all supported domains.

        Returns:
            List of domain information dicts
        """
        domains = []
        for domain in ["sales", "finance", "operations"]:
            info = self.router.get_domain_info(domain)
            if info:
                domains.append(info)
        return domains

    def process_query_with_trace(self, query: str) -> Dict[str, Any]:
        """
        Process query and return detailed execution trace.

        Includes intermediate steps for debugging and understanding.

        Args:
            query: Natural language query

        Returns:
            Dict with result and execution trace
        """
        trace = {
            "query": query,
            "steps": [],
        }

        # Step 1: Routing
        logger.debug("Step 1: Routing query")
        domain, confidence = self.router.route(query)
        trace["steps"].append({
            "step": "routing",
            "domain": domain,
            "confidence": confidence,
        })

        # Step 2: Domain agent processing
        logger.debug(f"Step 2: Processing with {domain} agent")
        agent = self.domain_agents.get(domain)
        if not agent:
            trace["error"] = f"Unknown domain: {domain}"
            trace["state"] = QueryState.ERROR.value
            return trace

        try:
            result = agent.process_query(query)
            trace["steps"].append({
                "step": "agent_processing",
                "domain": domain,
                "views": result.get("views", []),
                "filters": result.get("filters", {}),
                "aggregations": result.get("aggregations", {}),
            })

            # Step 3: Validation
            logger.debug("Step 3: Validation")
            trace["steps"].append({
                "step": "validation",
                "status": "passed" if not result.get("error") else "failed",
                "errors": result.get("error") if isinstance(result.get("error"), list) else [],
            })

            # Step 4: Execution
            logger.debug("Step 4: Execution")
            trace["steps"].append({
                "step": "execution",
                "row_count": result.get("row_count", 0),
                "confidence": result.get("confidence", 0),
            })

            trace["result"] = result
            trace["state"] = QueryState.COMPLETE.value
            trace["domain"] = domain

            return trace

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            trace["error"] = str(e)
            trace["state"] = QueryState.ERROR.value
            return trace
