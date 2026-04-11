"""
Dynamic Domain Agent Factory

Builds a DynamicDomainAgent from a DomainConfig so that newly-registered
domains participate in query routing and execution without code changes.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.agents.domain.base_domain import BaseDomainAgent, _build_interpret_prompt
from app.database.connection import DbConnection
from app.onboarding.models import DomainConfig
from app.query.builder import QueryBuilder
from app.views.models import QueryRequest
from app.views.registry import ViewRegistry

logger = logging.getLogger(__name__)


class DynamicDomainAgent(BaseDomainAgent):
    """
    A domain agent constructed at runtime from a DomainConfig.

    Inherits all LLM-interpretation, regex fallback, and execute logic
    from BaseDomainAgent — only the domain identity and available views
    come from the DomainConfig.
    """

    def __init__(
        self,
        config: DomainConfig,
        registry: ViewRegistry,
        db: DbConnection,
        builder: QueryBuilder,
    ) -> None:
        super().__init__(
            domain=config.name,
            registry=registry,
            db=db,
            builder=builder,
        )
        self._config = config

    # ------------------------------------------------------------------
    # Required abstract method
    # ------------------------------------------------------------------

    def process_query(
        self,
        natural_language_query: str,
        context_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a query for this dynamic domain.

        Tries LLM interpretation first, falls back to a keyword-based
        view selection using the configured view_names.
        """
        # Try LLM interpretation
        request = self._try_llm_interpret(natural_language_query, context_summary)

        if request is None:
            # Fallback: use all configured views
            available = [
                v for v in self._config.view_names
                if self.registry.get_view(v)
            ]
            if not available:
                return {
                    "error": f"No accessible views found for domain {self.domain!r}. "
                             f"Ensure view_names are registered in the view registry.",
                    "confidence": 0.0,
                    "views": [],
                    "row_count": 0,
                }
            request = QueryRequest(
                selected_views=available[:1],  # start with first view
                limit=100,
            )

        try:
            result = self.execute_query_request(request)
            result["confidence"] = 0.75
            return result
        except Exception as e:
            logger.error(f"Dynamic domain {self.domain} query failed: {e}")
            return {
                "error": str(e),
                "confidence": 0.0,
                "views": getattr(request, "selected_views", []),
                "row_count": 0,
            }


def build_agent(
    config: DomainConfig,
    registry: ViewRegistry,
    db: DbConnection,
    builder: QueryBuilder,
) -> DynamicDomainAgent:
    """Factory function — builds a DynamicDomainAgent from a DomainConfig."""
    return DynamicDomainAgent(config=config, registry=registry, db=db, builder=builder)
