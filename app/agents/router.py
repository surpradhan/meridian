"""
Request Router Agent

Routes incoming natural language queries to the appropriate domain agent.
Detects which domain (Sales, Finance, Operations) a query belongs to.
"""

import json
import logging
import re
from typing import Literal, Tuple
from app.views.registry import ViewRegistry
from app.agents.llm_client import get_llm

logger = logging.getLogger(__name__)

DOMAIN_DESCRIPTIONS = {
    "sales": (
        "questions about sales transactions, customers, products, revenue, orders, "
        "regions, territories, discounts, quantities sold"
    ),
    "finance": (
        "questions about general ledger, accounts, accounting entries, debits, credits, "
        "financial statements, account balances, GL transactions"
    ),
    "operations": (
        "questions about inventory, warehouses, shipments, logistics, stock levels, "
        "facilities, capacity, on-hand quantities, deliveries"
    ),
}


def _build_route_prompt(query: str) -> str:
    """Build the routing classification prompt without using str.format() on user input."""
    return (
        "You are a routing agent for MERIDIAN, a business intelligence platform.\n"
        "Classify the user's query into exactly one of these business domains:\n\n"
        f"- sales: {DOMAIN_DESCRIPTIONS['sales']}\n"
        f"- finance: {DOMAIN_DESCRIPTIONS['finance']}\n"
        f"- operations: {DOMAIN_DESCRIPTIONS['operations']}\n\n"
        'Return ONLY a JSON object with these fields:\n'
        '  "domain": one of "sales", "finance", "operations"\n'
        '  "confidence": float 0.0-1.0 (how certain you are)\n'
        '  "reasoning": one-sentence explanation\n\n'
        f"Query: {query}"
    )


class RouterAgent:
    """
    Routes queries to appropriate domain agents.

    Analyzes natural language queries and determines which business domain
    they pertain to (sales, finance, operations).

    Uses GPT-4 for classification when an OpenAI API key is configured,
    with keyword-based scoring as a fallback.
    """

    def __init__(self, registry: ViewRegistry):
        """
        Initialize the router agent.

        Args:
            registry: ViewRegistry instance for view information
        """
        self.registry = registry
        logger.debug("RouterAgent initialized")

        # Domain-specific keywords (used as fallback)
        self.domain_keywords = {
            "sales": {
                "keywords": [
                    "sales",
                    "sold",
                    "customer",
                    "order",
                    "product",
                    "region",
                    "territory",
                    "revenue",
                ],
                "views": ["sales_fact", "customer_dim", "product_dim"],
            },
            "finance": {
                "keywords": [
                    "ledger",
                    "account",
                    "transaction",
                    "gl",
                    "debit",
                    "credit",
                    "balance",
                    "accounting",
                    "financial",
                ],
                "views": ["ledger_fact", "account_dim"],
            },
            "operations": {
                "keywords": [
                    "inventory",
                    "warehouse",
                    "shipment",
                    "stock",
                    "logistics",
                    "location",
                    "quantity",
                ],
                "views": ["inventory_fact", "warehouse_dim", "shipment_fact"],
            },
        }

    def route(self, query: str) -> Tuple[Literal["sales", "finance", "operations"], float]:
        """
        Determine which domain a query belongs to.

        Tries LLM classification first; falls back to keyword scoring.

        Args:
            query: Natural language query

        Returns:
            Tuple of (domain, confidence)
        """
        llm = get_llm()
        if llm is not None:
            try:
                return self._try_llm_route(query, llm)
            except Exception as e:
                logger.warning(f"LLM routing failed, falling back to keyword routing: {e}")

        return self._keyword_route(query)

    def _try_llm_route(
        self, query: str, llm: object
    ) -> Tuple[Literal["sales", "finance", "operations"], float]:
        """Classify the query domain using GPT-4."""
        prompt = _build_route_prompt(query)
        response = llm.invoke(prompt)  # type: ignore[union-attr]
        content = response.content if hasattr(response, "content") else str(response)

        # Extract JSON — handle markdown code fences if present
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            raise ValueError(f"LLM did not return valid JSON: {content!r}")

        parsed = json.loads(json_match.group())
        domain = parsed.get("domain", "").lower()
        if domain not in ("sales", "finance", "operations"):
            raise ValueError(f"LLM returned unknown domain: {domain!r}")

        # Clamp confidence to [0, 1] in case LLM returns out-of-range value
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
        reasoning = parsed.get("reasoning", "")
        logger.info(
            f"LLM routed query to '{domain}' (confidence={confidence:.2f}): {reasoning}"
        )
        return domain, confidence  # type: ignore[return-value]

    def _keyword_route(
        self, query: str
    ) -> Tuple[Literal["sales", "finance", "operations"], float]:
        """Classify the query domain using keyword scoring."""
        query_lower = query.lower()

        scores = {domain: 0 for domain in ["sales", "finance", "operations"]}

        for domain, info in self.domain_keywords.items():
            for keyword in info["keywords"]:
                if keyword in query_lower:
                    scores[domain] += 1

        for domain, info in self.domain_keywords.items():
            for view in info["views"]:
                if view.replace("_", " ") in query_lower or view in query_lower:
                    scores[domain] += 2

        max_domain = max(scores, key=scores.get)
        max_score = scores[max_domain]

        total_score = sum(scores.values())
        if total_score == 0:
            confidence = 0.33
            max_domain = "sales"
            logger.warning(
                "No domain keywords matched — defaulting to 'sales' domain. "
                "Consider refining the query with domain-specific terms."
            )
        else:
            confidence = max_score / total_score

        logger.info(
            f"Keyword-routed query to '{max_domain}' domain with confidence {confidence:.2f}"
        )
        logger.debug(f"Domain scores: {scores}")

        return max_domain, confidence  # type: ignore[return-value]

    def get_domain_info(self, domain: str) -> dict:
        """
        Get information about a domain.

        Args:
            domain: Domain name (sales, finance, operations)

        Returns:
            Dict with domain information
        """
        if domain not in self.domain_keywords:
            return {}

        info = self.domain_keywords[domain]
        views = [self.registry.get_view(v) for v in info["views"]]
        views = [v for v in views if v is not None]

        return {
            "domain": domain,
            "keywords": info["keywords"],
            "views": [v.name for v in views],
            "view_count": len(views),
        }
