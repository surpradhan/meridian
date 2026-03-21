"""
Operations Domain Agent

Handles natural language queries related to operational data.
Understands operations-specific concepts like inventory, warehouses, shipments, etc.
"""

import logging
import re
from typing import Dict, Any, List
from app.views.models import QueryRequest
from app.agents.domain.base_domain import BaseDomainAgent

logger = logging.getLogger(__name__)


class OperationsAgent(BaseDomainAgent):
    """
    Agent for operations domain queries.

    Handles questions about:
    - Inventory levels
    - Warehouse locations
    - Shipments and logistics
    - Stock management
    """

    def __init__(self, registry, db, builder):
        """Initialize Operations agent."""
        super().__init__("operations", registry, db, builder)

        # Operations-specific keyword mappings
        # Note: "quantity" removed from inventory_fact — "inventory"/"stock"/"on hand" are
        #   sufficient and "quantity" was causing invalid joins with shipment_fact.
        # Note: "warehouse" removed from inventory_fact — should only trigger warehouse_dim
        #   to avoid selecting both fact tables which have no join relationship.
        self.view_keywords = {
            "inventory_fact": ["inventory", "stock", "on hand"],
            "warehouse_dim": ["warehouse", "location", "facility", "capacity"],
            "shipment_fact": ["shipment", "shipped", "ship", "delivery", "logistics", "shipping"],
        }

        # Cross-domain views that operations queries may need
        # product_dim lives in 'sales' domain but has joins to inventory_fact/shipment_fact
        self.cross_domain_views = {
            "product_dim": ["product", "products", "item", "items", "sku"],
        }

        self.aggregation_keywords = {
            "SUM": ["total", "sum", "overall"],
            "COUNT": ["how many", "count", "number of"],
            "AVG": ["average", "avg"],
            "MIN": ["minimum", "lowest"],
            "MAX": ["maximum", "highest"],
        }

    def process_query(self, natural_language_query: str) -> Dict[str, Any]:
        """
        Process a natural language operations query.

        Examples:
        - "What is the total inventory across all warehouses?"
        - "Show me shipments from the New York warehouse"
        - "Which products have low stock levels?"

        Args:
            natural_language_query: Natural language question

        Returns:
            Dict with result, SQL, confidence, etc.
        """
        logger.info(f"Processing operations query: {natural_language_query}")

        query_lower = natural_language_query.lower()

        try:
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
            confidence = self._calculate_confidence(natural_language_query, result)
            result["confidence"] = confidence

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

        Args:
            query_lower: Lowercase query string

        Returns:
            List of relevant view names
        """
        identified = set()

        # Identify based on primary operations view keywords
        for view_name, keywords in self.view_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    identified.add(view_name)
                    break

        # Check cross-domain views (e.g. product_dim from the sales domain)
        for view_name, keywords in self.cross_domain_views.items():
            for keyword in keywords:
                if keyword in query_lower:
                    identified.add(view_name)
                    break

        # If no views identified, default to inventory
        if not identified:
            identified.add("inventory_fact")

        # Ensure fact tables come first (required for JOIN ordering)
        fact_tables = [v for v in identified if v.endswith("_fact")]
        dim_tables = [v for v in identified if not v.endswith("_fact")]
        return fact_tables + dim_tables

    def _identify_filters(self, query_lower: str, views: List[str], original_query: str = "") -> Dict[str, Any]:
        """
        Identify WHERE clause filters from the query.

        Args:
            query_lower: Lowercase query string
            views: List of views being queried

        Returns:
            Dict of column: value filters
        """
        filters = {}
        query_for_names = original_query if original_query else query_lower

        # Warehouse name filter — only match quoted names (e.g. warehouse 'Dallas DC')
        # Run on original query to preserve case of the quoted value
        # Unquoted "warehouse in chicago" is handled by the location filter below
        warehouse_match = re.search(r"warehouse\s+(['\"])([^'\"]+)\1", query_for_names, re.IGNORECASE)
        if warehouse_match:
            filters["name"] = warehouse_match.group(2).strip()
            logger.debug(f"Identified warehouse name filter: {filters['name']}")

        # Location filter — match "at/in <place> warehouse" or "location <name>"
        skip_words = {"each", "every", "all", "the", "a", "any", "our", "their", "this", "that"}
        location_match = re.search(
            r"\b(?:in|at)\s+(['\"]?)(\w[\w\s]*?)\1\s+warehouse\b", query_lower
        )
        if location_match:
            loc_candidate = location_match.group(2).strip()
            # Skip if the entire captured string is a stop word
            if loc_candidate in skip_words:
                location_match = None
            else:
                # Strip leading stop words (e.g. "the chicago" → "chicago")
                for word in ("the", "a", "an"):
                    if loc_candidate.startswith(word + " "):
                        loc_candidate = loc_candidate[len(word) + 1:]
                        break
                filters["location"] = loc_candidate
                logger.debug(f"Identified location filter: {loc_candidate}")
                location_match = None  # already handled

        if location_match is None and "location" in query_lower:
            location_match = re.search(r"location\s+(['\"]?)([^'\"]+)\1", query_lower)
        if location_match:
            location = location_match.group(2).strip()
            filters["location"] = location
            logger.debug(f"Identified location filter: {location}")

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

        # Check for aggregation keywords
        # "capacity" maps to warehouse_dim.capacity — a warehouse property, not inventory.
        # Use MAX to get the correct per-warehouse value without duplication from JOINs.
        if "capacity" in query_lower:
            aggregations["capacity"] = "MAX"
            # Remove inventory_fact from views — capacity belongs to warehouse_dim only,
            # and joining through inventory_fact duplicates the capacity value per row.
            views[:] = [v for v in views if v != "inventory_fact"]
            logger.debug("Identified aggregation: MAX(capacity); dropped inventory_fact")
        else:
            for agg_func, keywords in self.aggregation_keywords.items():
                for keyword in keywords:
                    if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                        # Use the appropriate quantity column based on selected views
                        if "shipment_fact" in views and "inventory_fact" not in views:
                            agg_col = "quantity"
                        else:
                            agg_col = "quantity_on_hand"
                        aggregations[agg_col] = agg_func
                        logger.debug(f"Identified aggregation: {agg_func}({agg_col})")
                        break

        # Check for GROUP BY keywords using fragment-based parsing
        group_keywords = {
            "warehouse": "warehouse_id",
            "location": "location",
            "product": "product_id",
        }

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
        Calculate confidence score for query interpretation.

        Args:
            query: Original query string
            result: Query result dict

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.5

        # Increase if we got results
        if result.get("row_count", 0) > 0:
            confidence += 0.2

        # Increase if explicit operations keywords matched
        if any(
            keyword in query.lower()
            for keyword in ["warehouse", "inventory", "shipment", "stock"]
        ):
            confidence += 0.2

        # Increase if we have aggregations
        if "aggregations" in result:
            confidence += 0.1

        return min(1.0, confidence)
