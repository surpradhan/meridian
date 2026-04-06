"""
Base Domain Agent

Abstract base class for domain-specific agents (Sales, Finance, Operations).
Provides common functionality like view discovery, query building, and execution.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.views.models import QueryRequest
from app.views.registry import ViewRegistry
from app.query.builder import QueryBuilder
from app.database.connection import DbConnection
from app.agents.llm_client import get_llm

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

    def retry(*args, **kwargs):  # type: ignore[misc]
        def decorator(func):
            return func
        return decorator

    def stop_after_attempt(n):  # type: ignore[misc]
        return None

    def wait_exponential(**kwargs):  # type: ignore[misc]
        return None

    def retry_if_exception_type(exc):  # type: ignore[misc]
        return None

logger = logging.getLogger(__name__)


def _build_interpret_prompt(
    domain: str,
    schema_json: str,
    query: str,
    context_summary: Optional[str] = None,
) -> str:
    """Build the query interpretation prompt without using str.format() on user input."""
    context_section = ""
    if context_summary and context_summary != "No previous context.":
        context_section = (
            f"\nConversation context (use to resolve references like 'that', 'same', 'it'):\n"
            f"{context_summary}\n"
        )

    return (
        f"You are a query interpreter for the {domain} domain of MERIDIAN BI platform.\n\n"
        f"Available view schemas (domain: {domain}):\n"
        f"{schema_json}\n"
        f"{context_section}\n"
        f'Extract query parameters from this natural language question:\n"{query}"\n\n'
        "Return ONLY a JSON object with these fields:\n"
        '  "selected_views": list of view names from the schema to use (fact tables first)\n'
        '  "filters": dict mapping column_name to value for WHERE filters (empty dict if none)\n'
        '  "aggregations": dict mapping column_name to function (SUM|COUNT|AVG|MIN|MAX) (empty dict if none)\n'
        '  "group_by": list of column names for GROUP BY (empty list if none)\n\n'
        "Rules:\n"
        "- Only use view names and column names that appear in the schema above\n"
        "- At least one view must be selected\n"
        "- Extract exact string values from the query for filters (preserve case of proper nouns)\n"
        "- Fact tables (names ending in _fact) must appear before dimension tables in selected_views"
        + (
            "\n- Use conversation context to resolve pronouns or references to prior results"
            if context_summary and context_summary != "No previous context."
            else ""
        )
    )


class BaseDomainAgent(ABC):
    """
    Abstract base for domain-specific agents.

    Each domain (Sales, Finance, Operations) has an agent that understands
    the specific views and business logic for that domain.

    Attributes:
        domain: Name of the business domain (e.g., "sales", "finance")
        registry: ViewRegistry for accessing view metadata
        db: Database connection for query execution
        builder: QueryBuilder for constructing SQL queries
    """

    def __init__(
        self,
        domain: str,
        registry: ViewRegistry,
        db: DbConnection,
        builder: QueryBuilder,
    ):
        """
        Initialize a domain agent.

        Args:
            domain: Domain name (sales, finance, operations)
            registry: ViewRegistry instance
            db: DbConnection instance
            builder: QueryBuilder instance
        """
        self.domain = domain
        self.registry = registry
        self.db = db
        self.builder = builder

        logger.info(f"Initialized {domain} agent")

    def _get_schema_for_llm(self) -> str:
        """Build a compact schema description for LLM prompts."""
        views = self.registry.get_views_by_domain(self.domain)
        schema: Dict[str, Any] = {}
        for view in views:
            schema[view.name] = {
                "description": view.description,
                "type": view.view_type,
                "columns": [
                    {
                        "name": col.name,
                        "type": col.data_type,
                        "description": col.description,
                    }
                    for col in view.columns
                ],
            }
        return json.dumps(schema, indent=2)

    def _try_llm_interpret(
        self,
        query: str,
        context_summary: Optional[str] = None,
    ) -> Optional[QueryRequest]:
        """
        Use GPT-4 to interpret the natural language query into a QueryRequest.

        Args:
            query: Natural language query
            context_summary: Optional conversation context for multi-turn resolution

        Returns:
            QueryRequest if successful, None if LLM unavailable or parsing failed.
            Does NOT catch execution errors — callers must handle those separately
            so they can fall back to the regex pipeline on a bad QueryRequest.
        """
        llm = get_llm()
        if llm is None:
            return None

        try:
            schema_json = self._get_schema_for_llm()
            prompt = _build_interpret_prompt(self.domain, schema_json, query, context_summary)
            response = llm.invoke(prompt)  # type: ignore[union-attr]
            content = response.content if hasattr(response, "content") else str(response)

            # Extract JSON — handle markdown code fences if present
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if not json_match:
                raise ValueError(f"LLM did not return valid JSON: {content!r}")

            parsed = json.loads(json_match.group())

            selected_views = parsed.get("selected_views") or []
            if not selected_views:
                raise ValueError("LLM returned empty selected_views")

            request = QueryRequest(
                selected_views=selected_views,
                filters=parsed.get("filters") or None,
                aggregations=parsed.get("aggregations") or None,
                group_by=parsed.get("group_by") or None,
                limit=100,
            )
            logger.info(
                f"LLM interpreted query for {self.domain}: "
                f"views={selected_views}, filters={request.filters}, "
                f"aggs={request.aggregations}, group_by={request.group_by}"
            )
            return request

        except Exception as e:
            logger.warning(f"LLM query interpretation failed for {self.domain}, using regex: {e}")
            return None

    @abstractmethod
    def process_query(
        self,
        natural_language_query: str,
        context_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a natural language query for this domain.

        Subclasses must implement specific logic for understanding
        domain-specific questions and mapping them to views/tables.

        Args:
            natural_language_query: Natural language question from user

        Returns:
            Dict with:
            - 'result': Query result rows
            - 'sql': SQL query used
            - 'views': Views accessed
            - 'row_count': Number of rows returned
            - 'confidence': Confidence score (0-1)
        """
        pass

    def get_available_views(self) -> List[str]:
        """
        Get all views available in this domain.

        Returns:
            List of view names
        """
        views = self.registry.get_views_by_domain(self.domain)
        return [v.name for v in views]

    def get_view_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all views in this domain.

        Returns:
            Dict mapping view name to metadata
        """
        views = self.registry.get_views_by_domain(self.domain)
        summary = {}

        for view in views:
            summary[view.name] = {
                "type": view.view_type,
                "row_count": view.row_count,
                "columns": [col.name for col in view.columns],
                "description": view.description,
            }

        return summary

    def find_relevant_views(self, query_keywords: List[str]) -> List[str]:
        """
        Find views relevant to a query based on keywords.

        Matches keywords against view names and descriptions.

        Args:
            query_keywords: List of keywords from natural language query

        Returns:
            List of relevant view names
        """
        relevant_views = []
        available_views = self.get_available_views()

        for view_name in available_views:
            view = self.registry.get_view(view_name)
            if not view:
                continue

            # Check if any keyword matches view name or description
            view_text = (view.name + " " + view.description).lower()

            for keyword in query_keywords:
                if keyword.lower() in view_text:
                    relevant_views.append(view_name)
                    break

        return relevant_views

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        # Only retry transient runtime errors (e.g. DB connection drops).
        # ValueError means bad query input — retrying won't help and adds latency.
        retry=retry_if_exception_type(RuntimeError),
        reraise=True,
    )
    def execute_query_request(self, request: QueryRequest) -> Dict[str, Any]:
        """
        Execute a QueryRequest and return results.

        Args:
            request: QueryRequest with views, filters, aggregations, etc.

        Returns:
            Dict with result data and metadata

        Raises:
            ValueError: If query is invalid
            Exception: If database execution fails
        """
        # Validate views
        is_valid, msg = self.registry.validate_view_combination(request.selected_views)
        if not is_valid:
            raise ValueError(f"Invalid view combination: {msg}")

        # Build SQL query
        sql = self.builder.build_query(request)
        logger.info(f"Executing query: {sql}")

        # Execute query
        results = self.db.execute_query(sql)

        return {
            "result": results,
            "sql": sql,
            "views": request.selected_views,
            "row_count": len(results),
        }

    def suggest_filters(self, view_name: str) -> Dict[str, List[str]]:
        """
        Suggest filter options for a view.

        In production, would analyze actual data to suggest common values.

        Args:
            view_name: Name of the view

        Returns:
            Dict mapping column name to suggested filter values
        """
        view = self.registry.get_view(view_name)
        if not view:
            return {}

        suggestions = {}

        # For now, suggest columns that are good for filtering
        for col in view.columns:
            # String and small integer columns are good for filtering
            if col.data_type.upper() in ["VARCHAR", "TEXT", "INT"]:
                suggestions[col.name] = ["(suggested values from data)"]

        return suggestions

    def get_join_paths(self, from_view: str, to_view: str) -> Optional[List[str]]:
        """
        Find a path of views connecting two views via joins.

        Args:
            from_view: Starting view name
            to_view: Target view name

        Returns:
            List of view names in the path, or None if not connected
        """
        reachable = self.registry.get_reachable_views(from_view)

        if to_view not in reachable:
            return None

        # Simple path: direct join if it exists
        if self.registry.find_joins(from_view, to_view):
            return [from_view, to_view]

        # TODO: Implement full path-finding algorithm for multi-hop joins
        return None

    def __repr__(self) -> str:
        """String representation of agent."""
        return f"{self.__class__.__name__}(domain={self.domain})"
