"""
Sales Domain Agent

Handles natural language queries related to sales data.
Understands sales-specific concepts like customers, products, regions, etc.
"""

import logging
import re
from typing import Dict, Any, List
from app.views.models import QueryRequest
from app.agents.domain.base_domain import BaseDomainAgent

logger = logging.getLogger(__name__)


class SalesAgent(BaseDomainAgent):
    """
    Agent for sales domain queries.

    Handles questions about:
    - Sales transactions (amount, quantity, date)
    - Customers (name, region, segment)
    - Products (name, category, price)
    - Trends and comparisons
    """

    def __init__(self, registry, db, builder):
        """Initialize Sales agent."""
        super().__init__("sales", registry, db, builder)

        # Sales-specific keyword mappings
        self.view_keywords = {
            "sales_fact": ["sales", "transactions", "orders", "sold", "amount", "quantity"],
            "customer_dim": ["customer", "clients", "accounts", "who", "buyer", "region", "segment"],
            "product_dim": ["product", "products", "items", "goods", "merchandise", "category"],
        }

        self.aggregation_keywords = {
            "SUM": ["total", "sum", "aggregate", "overall"],
            "COUNT": ["how many", "count", "number of"],
            "AVG": ["average", "avg", "mean"],
            "MIN": ["minimum", "min", "lowest"],
            "MAX": ["maximum", "max", "highest"],
        }

    def process_query(self, natural_language_query: str) -> Dict[str, Any]:
        """
        Process a natural language sales query.

        Examples:
        - "How many sales were made in the WEST region?"
        - "What was the total sales amount by customer?"
        - "Show me the top products by sales"

        Args:
            natural_language_query: Natural language question

        Returns:
            Dict with result, SQL, confidence, etc.
        """
        logger.info(f"Processing sales query: {natural_language_query}")

        query_lower = natural_language_query.lower()

        try:
            # Try LLM interpretation first; fall back to regex on failure or unavailability.
            # Two-stage fallback: _try_llm_interpret catches parse/API errors; the inner
            # try/except below catches execution failures from a bad LLM-generated request.
            llm_request = self._try_llm_interpret(natural_language_query)
            if llm_request is not None:
                try:
                    result = self.execute_query_request(llm_request)
                    result["confidence"] = self._calculate_confidence(natural_language_query, result)
                    result["interpretation_method"] = "llm"
                    logger.info(f"LLM query executed successfully. Rows returned: {result['row_count']}")
                    return result
                except Exception as exec_err:
                    logger.warning(
                        f"LLM-generated request failed ({exec_err}), falling back to regex"
                    )

            # Regex fallback
            # Step 1: Identify relevant views
            relevant_views = self._identify_views(query_lower)
            logger.debug(f"Identified views: {relevant_views}")

            # Step 2: Identify filters
            filters = self._identify_filters(query_lower, relevant_views, natural_language_query)
            logger.debug(f"Identified filters: {filters}")

            # Step 3: Identify aggregations and groupings
            aggregations, group_by = self._identify_aggregations(query_lower, relevant_views)
            logger.debug(f"Identified aggregations: {aggregations}, groupings: {group_by}")

            # Step 4: Build and execute query
            request = QueryRequest(
                selected_views=relevant_views,
                filters=filters,
                aggregations=aggregations,
                group_by=group_by,
                limit=100,
            )

            result = self.execute_query_request(request)

            # Add confidence score
            confidence = self._calculate_confidence(natural_language_query, result)
            result["confidence"] = confidence
            result["interpretation_method"] = "regex"

            logger.info(f"Query executed successfully. Rows returned: {result['row_count']}")

            return result

        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return {
                "error": str(e),
                "confidence": 0.0,
                "result": [],
            }

    def _identify_views(self, query_lower: str) -> List[str]:
        """
        Identify which views are relevant to the query.

        Uses keyword matching against view names and descriptions.
        Only includes explicitly mentioned views or required joins.

        Args:
            query_lower: Lowercase query string

        Returns:
            List of relevant view names
        """
        identified = set()

        # Always include sales_fact as base
        identified.add("sales_fact")

        # Check for explicit keywords for OTHER views
        for view_name, keywords in self.view_keywords.items():
            if view_name == "sales_fact":
                continue  # Already included

            for keyword in keywords:
                if keyword in query_lower:
                    identified.add(view_name)
                    break

        # Ensure fact table is always first (required for JOIN ordering)
        result = ["sales_fact"]
        result.extend(v for v in identified if v != "sales_fact")
        return result

    def _identify_filters(self, query_lower: str, views: List[str], original_query: str = "") -> Dict[str, Any]:
        """
        Identify WHERE clause filters from the query.

        Looks for patterns like "in [region]", "for [customer]", "by [category]"

        Args:
            query_lower: Lowercase query string
            views: List of views being queried
            original_query: Original (case-preserved) query for extracting quoted values

        Returns:
            Dict of column: value filters
        """
        filters = {}
        query_for_names = original_query if original_query else query_lower

        # Region filter - matches "region WEST" or "WEST region"
        region_match = re.search(r"(?:in\s+)?(?:the\s+)?(\w+)\s+region\b|\bregion\s+(\w+)", query_lower)
        if region_match:
            region = (region_match.group(1) or region_match.group(2)).upper()
            filters["region"] = region
            logger.debug(f"Identified region filter: {region}")

        # Customer filter - run on original query to preserve case of quoted values
        customer_match = re.search(r"customer\s+['\"]([^'\"]+)['\"]", query_for_names, re.IGNORECASE)
        if customer_match:
            filters["name"] = customer_match.group(1)
            logger.debug(f"Identified customer filter: {customer_match.group(1)}")

        # Product filter - run on original query to preserve case of quoted values
        product_match = re.search(r"product\s+['\"]([^'\"]+)['\"]", query_for_names, re.IGNORECASE)
        if product_match:
            filters["name"] = product_match.group(1)
            logger.debug(f"Identified product filter: {product_match.group(1)}")

        return filters

    def _identify_aggregations(
        self, query_lower: str, views: List[str]
    ) -> tuple[Dict[str, str], List[str]]:
        """
        Identify aggregation functions and GROUP BY columns.

        Args:
            query_lower: Lowercase query string
            views: List of views being queried

        Returns:
            Tuple of (aggregations dict, group_by list)
        """
        aggregations = {}
        group_by = []

        # Check for aggregation keywords using word-boundary matching to avoid
        # false positives (e.g. "count" matching inside "account" or "discount")
        for agg_func, keywords in self.aggregation_keywords.items():
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                    # Infer which column to aggregate
                    if agg_func in ["SUM", "AVG", "MIN", "MAX"]:
                        aggregations["amount"] = agg_func
                    elif agg_func == "COUNT":
                        aggregations["sale_id"] = "COUNT"

                    logger.debug(f"Identified aggregation: {agg_func}")
                    break

        # Group by human-readable name columns rather than raw IDs so results
        # are immediately meaningful to users (Bug 5 fix).
        group_keywords = {
            "customer": "name",     # resolves to customer_dim.name
            "region": "region",     # resolves to customer_dim.region
            "product": "name",      # resolves to product_dim.name
            "category": "category", # resolves to product_dim.category
            "date": "date",
        }

        # Fragment-based "by X and Y" parser — handles multi-dimension grouping
        # where dimensions are joined with "and" or "," instead of separate "by X" (Bug 7 fix).
        by_match = re.search(
            r'\b(?:by|per)\s+(.+?)(?:\s+(?:where|having|order|limit)|$)',
            query_lower
        )
        if by_match:
            by_fragment = by_match.group(1)
            parts = re.split(r'\s+and\s+|,\s*', by_fragment)
            for part in parts:
                part_stripped = part.strip()
                for keyword, column in group_keywords.items():
                    if keyword in part_stripped and column not in group_by:
                        group_by.append(column)
                        logger.debug(f"Identified group by: {column}")

        return aggregations, group_by

    def _calculate_confidence(self, query: str, result: Dict[str, Any]) -> float:
        """
        Calculate confidence score for the query interpretation.

        Returns a score 0-1 indicating how confident we are in the answer.

        Args:
            query: Original query string
            result: Query result dict

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.5  # Base confidence

        # Increase confidence if we got results
        if result.get("row_count", 0) > 0:
            confidence += 0.2

        # Increase if explicit keywords matched
        if any(keyword in query.lower() for keyword in ["sales", "customer", "product"]):
            confidence += 0.2

        # Increase if we have aggregations (more specific query)
        if "aggregations" in result:
            confidence += 0.1

        return min(1.0, confidence)

    def clarify_query(self, query: str) -> Dict[str, Any]:
        """
        Provide clarification or suggestions for a query.

        Useful when we're not confident or when user wants to explore.

        Args:
            query: Original query string

        Returns:
            Dict with suggestions, available views, etc.
        """
        return {
            "available_views": self.get_available_views(),
            "view_summary": self.get_view_summary(),
            "sample_queries": [
                "How many sales were made in the WEST region?",
                "What was the total sales amount by customer?",
                "Show me the top 10 products by quantity sold",
            ],
        }
