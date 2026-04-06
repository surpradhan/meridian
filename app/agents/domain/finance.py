"""
Finance Domain Agent

Handles natural language queries related to financial data.
Understands finance-specific concepts like accounts, transactions, GL balances, etc.
"""

import logging
import re
from typing import Dict, Any, List
from app.views.models import QueryRequest
from app.agents.domain.base_domain import BaseDomainAgent

logger = logging.getLogger(__name__)


class FinanceAgent(BaseDomainAgent):
    """
    Agent for finance domain queries.

    Handles questions about:
    - General ledger transactions
    - Account balances
    - Transaction types (debit/credit)
    - Period-based reporting
    """

    def __init__(self, registry, db, builder):
        """Initialize Finance agent."""
        super().__init__("finance", registry, db, builder)

        # Finance-specific keyword mappings
        self.view_keywords = {
            "ledger_fact": ["ledger", "transaction", "gl", "journal", "entry", "posting"],
            "account_dim": ["account", "accounts", "chart", "coa"],
        }

        self.aggregation_keywords = {
            "SUM": ["total", "sum", "balance", "amount"],
            "COUNT": ["how many", "count", "number of"],
            "AVG": ["average", "avg", "mean"],
        }

    def process_query(self, natural_language_query: str) -> Dict[str, Any]:
        """
        Process a natural language finance query.

        Examples:
        - "What is the balance in the cash account?"
        - "Show me all GL transactions for this period"
        - "Total debits vs credits by account type"

        Args:
            natural_language_query: Natural language question

        Returns:
            Dict with result, SQL, confidence, etc.
        """
        logger.info(f"Processing finance query: {natural_language_query}")

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
            filters = self._identify_filters(query_lower, relevant_views)
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

        Args:
            query_lower: Lowercase query string

        Returns:
            List of relevant view names
        """
        identified = set()

        # Always include ledger_fact as base
        identified.add("ledger_fact")

        # Check for explicit keywords for other views
        for view_name, keywords in self.view_keywords.items():
            if view_name == "ledger_fact":
                continue

            for keyword in keywords:
                if keyword in query_lower:
                    identified.add(view_name)
                    break

        # Ensure fact table is always first (required for JOIN ordering)
        result = ["ledger_fact"]
        result.extend(v for v in identified if v != "ledger_fact")
        return result

    def _identify_filters(self, query_lower: str, views: List[str]) -> Dict[str, Any]:
        """
        Identify WHERE clause filters from the query.

        Args:
            query_lower: Lowercase query string
            views: List of views being queried

        Returns:
            Dict of column: value filters
        """
        filters = {}

        # Account number filter — only match quoted names or numeric codes
        # e.g. "account '1000'" or "account 1000", but NOT "account type asset"
        account_match = re.search(r"account\s+(['\"])([^'\"]+)\1", query_lower)
        if not account_match:
            account_match = re.search(r"account\s+(\d[\d\-]+)", query_lower)
        if account_match:
            idx = 2 if account_match.lastindex and account_match.lastindex >= 2 else 1
            filters["account_number"] = account_match.group(idx).strip()
            logger.debug(f"Identified account filter: {filters['account_number']}")

        # Account type filter — match known account type names directly
        known_account_types = {"asset", "liability", "equity", "revenue", "expense"}
        for type_name in known_account_types:
            if type_name in query_lower:
                filters["account_type"] = type_name.upper()
                logger.debug(f"Identified account type filter: {type_name.upper()}")
                break

        # Debit/Credit filter — when BOTH appear it's a comparison query (no filter)
        has_debit = "debit" in query_lower
        has_credit = "credit" in query_lower
        if has_debit and has_credit:
            # Comparison query — do not filter on one side; let GROUP BY handle it
            pass
        elif has_debit:
            filters["debit_credit"] = "DEBIT"
        elif has_credit:
            filters["debit_credit"] = "CREDIT"

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
        # false positives like "count" matching inside "account"
        for agg_func, keywords in self.aggregation_keywords.items():
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                    # For finance, typically aggregate on amount
                    aggregations["amount"] = agg_func
                    logger.debug(f"Identified aggregation: {agg_func}")
                    break

        # Check for GROUP BY keywords using fragment-based parsing
        # Handles "by X and Y" patterns, not just "by X" literals
        group_keywords = {
            "account": "account_id",
            "type": "account_type",
            "period": "date",
            "date": "date",
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

        # If both debit and credit present, group by debit_credit for comparison
        if "debit" in query_lower and "credit" in query_lower:
            if "debit_credit" not in group_by:
                group_by.append("debit_credit")
                logger.debug("Identified group by: debit_credit (comparison query)")

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

        # Increase if explicit finance keywords matched
        if any(keyword in query.lower() for keyword in ["account", "ledger", "transaction"]):
            confidence += 0.2

        # Increase if we have aggregations
        if "aggregations" in result:
            confidence += 0.1

        return min(1.0, confidence)
