"""
Request Router Agent

Routes incoming natural language queries to the appropriate domain agent.
Detects which domain (Sales, Finance, Operations) a query belongs to.
"""

import logging
from typing import Literal, Tuple
from app.views.registry import ViewRegistry

logger = logging.getLogger(__name__)


class RouterAgent:
    """
    Routes queries to appropriate domain agents.

    Analyzes natural language queries and determines which business domain
    they pertain to (sales, finance, operations).
    """

    def __init__(self, registry: ViewRegistry):
        """
        Initialize the router agent.

        Args:
            registry: ViewRegistry instance for view information
        """
        self.registry = registry
        logger.debug("RouterAgent initialized")

        # Domain-specific keywords
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

        Uses keyword matching and view mentions to classify the query.

        Args:
            query: Natural language query

        Returns:
            Tuple of (domain, confidence)
            domain: "sales", "finance", or "operations"
            confidence: 0-1 confidence score
        """
        query_lower = query.lower()

        # Score each domain
        scores = {domain: 0 for domain in ["sales", "finance", "operations"]}

        # Check for domain keywords
        for domain, info in self.domain_keywords.items():
            for keyword in info["keywords"]:
                if keyword in query_lower:
                    scores[domain] += 1

        # Check for view mentions
        for domain, info in self.domain_keywords.items():
            for view in info["views"]:
                if view.replace("_", " ") in query_lower or view in query_lower:
                    scores[domain] += 2  # View mentions are stronger signals

        # Determine winning domain
        max_domain = max(scores, key=scores.get)
        max_score = scores[max_domain]

        # Calculate confidence
        total_score = sum(scores.values())
        if total_score == 0:
            confidence = 0.33  # Equal probability — no domain-specific keywords found
            max_domain = "sales"  # Default to sales as a fallback
            logger.warning(
                "No domain keywords matched — defaulting to 'sales' domain. "
                "Consider refining the query with domain-specific terms."
            )
        else:
            confidence = max_score / total_score

        logger.info(
            f"Routed query to '{max_domain}' domain with confidence {confidence:.2f}"
        )
        logger.debug(f"Domain scores: {scores}")

        return max_domain, confidence

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
