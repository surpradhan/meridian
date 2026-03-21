"""
Base Domain Agent

Abstract base class for domain-specific agents (Sales, Finance, Operations).
Provides common functionality like view discovery, query building, and execution.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.views.models import QueryRequest
from app.views.registry import ViewRegistry
from app.query.builder import QueryBuilder
from app.database.connection import DbConnection

logger = logging.getLogger(__name__)


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

    @abstractmethod
    def process_query(self, natural_language_query: str) -> Dict[str, Any]:
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
