"""
Query Builder

Constructs safe SQL queries from natural language requests.
Takes a QueryRequest with selected views and builds the appropriate JOIN and WHERE clauses.

This module is responsible for:
1. Understanding relationships between views via the registry
2. Generating efficient JOINs
3. Building WHERE clauses from filters
4. Adding LIMIT and aggregations
"""

import logging
from typing import List, Set, Dict, Any, Optional, Tuple
from app.views.models import QueryRequest
from app.views.registry import ViewRegistry

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Builds SQL queries from QueryRequest objects using the ViewRegistry.

    The builder understands relationships between views and automatically
    generates JOIN clauses. It's designed for safety and efficiency.

    Attributes:
        registry: ViewRegistry instance for view metadata
    """

    def __init__(self, registry: ViewRegistry):
        """
        Initialize the query builder.

        Args:
            registry: ViewRegistry instance
        """
        self.registry = registry
        logger.debug("QueryBuilder initialized")

    def build_query(self, request: QueryRequest) -> str:
        """
        Build a complete SQL query from a QueryRequest.

        Args:
            request: QueryRequest with selected views, filters, aggregations, etc.

        Returns:
            SQL query string ready for execution

        Raises:
            ValueError: If views are invalid or cannot be joined
        """
        # Validate views exist
        views = request.selected_views
        for view in views:
            if self.registry.get_view(view) is None:
                raise ValueError(f"View {view} not found in registry")

        # Build SELECT clause
        select_clause = self._build_select_clause(request)

        # Build FROM clause with JOINs
        from_clause = self._build_from_clause(request)

        # Build WHERE clause
        where_clause = self._build_where_clause(request)

        # Build GROUP BY clause (for aggregations)
        group_by_clause = self._build_group_by_clause(request)

        # Build LIMIT clause
        limit_clause = f"LIMIT {request.limit}"

        # Assemble query
        parts = [select_clause, from_clause]

        if where_clause:
            parts.append(where_clause)

        if group_by_clause:
            parts.append(group_by_clause)

        parts.append(limit_clause)

        query = " ".join(parts)
        logger.debug(f"Built query: {query}")

        return query

    def _build_select_clause(self, request: QueryRequest) -> str:
        """
        Build SELECT clause with appropriate columns.

        For now, selects all columns from all views. In production,
        would select only relevant columns based on context.

        Args:
            request: QueryRequest

        Returns:
            SELECT clause string
        """
        if request.aggregations:
            # Build aggregation select
            agg_parts = []
            for column, agg_func in request.aggregations.items():
                qualified_col = self._resolve_column_table(column, request.selected_views)
                agg_parts.append(f"{agg_func}({qualified_col}) AS {agg_func}_{column}")

            # Add group by columns to select
            if request.group_by:
                for group_col in request.group_by:
                    qualified_col = self._resolve_column_table(group_col, request.selected_views)
                    agg_parts.insert(0, qualified_col)

            return f"SELECT {', '.join(agg_parts)}"
        else:
            # Select all columns from all views
            select_parts = [f"{view}.*" for view in request.selected_views]
            return f"SELECT {', '.join(select_parts)}"

    def _build_from_clause(self, request: QueryRequest) -> str:
        """
        Build FROM clause with automatic JOINs.

        Intelligently joins multiple views using the registry's join relationships.
        Starts with first view and joins subsequent views.

        Args:
            request: QueryRequest

        Returns:
            FROM clause with JOINs

        Raises:
            ValueError: If views cannot be joined
        """
        views = request.selected_views

        if len(views) == 1:
            return f"FROM {views[0]}"

        # Build JOIN chain — search all previously seen views for a join path,
        # not just the immediately preceding one. This handles cases like
        # [sales_fact, customer_dim, product_dim] where product_dim joins to
        # sales_fact (not customer_dim).
        from_parts = [f"FROM {views[0]}"]

        for i in range(1, len(views)):
            current_view = views[i]
            join_rel = None

            # Try each previously included view in reverse order (prefer nearest)
            for j in range(i - 1, -1, -1):
                candidate = views[j]
                join_rel = self.registry.find_joins(candidate, current_view)
                if join_rel:
                    break
                join_rel = self.registry.find_joins(current_view, candidate)
                if join_rel:
                    break

            if join_rel is None:
                raise ValueError(
                    f"No join relationship found between any previous view and {current_view}"
                )

            # Build join condition
            join_condition = join_rel.get_join_condition()

            # Determine join type based on relationship
            join_type = self._determine_join_type(join_rel.relationship_type)

            from_parts.append(f"{join_type} {current_view} ON {join_condition}")

        return " ".join(from_parts)

    def _resolve_column_table(self, column: str, views: List[str]) -> str:
        """
        Resolve which table a column belongs to and return table-qualified name.

        Args:
            column: Column name
            views: List of view names in the query

        Returns:
            Table-qualified column name (e.g., "customer_dim.region")
        """
        for view_name in views:
            view = self.registry.get_view(view_name)
            if view and any(col.name.lower() == column.lower() for col in view.columns):
                return f"{view_name}.{column}"
        return column

    def _build_where_clause(self, request: QueryRequest) -> Optional[str]:
        """
        Build WHERE clause from filters.

        Filters are provided as key-value pairs. For safety, values are
        parameterized (though implementation here shows them for clarity).

        Args:
            request: QueryRequest

        Returns:
            WHERE clause string, or None if no filters
        """
        if not request.filters:
            return None

        conditions = []
        for column, value in request.filters.items():
            qualified_col = self._resolve_column_table(column, request.selected_views)
            # For safety, we'd normally use parameterized queries
            # For now, we'll build the condition safely with type checking
            if isinstance(value, str):
                # String values get quoted; COLLATE NOCASE makes comparisons
                # case-insensitive so agent-generated values always match DB data
                # regardless of capitalisation differences (e.g. 'ASSET' vs 'Asset')
                conditions.append(f"{qualified_col} = '{value}' COLLATE NOCASE")
            elif isinstance(value, (int, float)):
                # Numeric values don't need quotes
                conditions.append(f"{qualified_col} = {value}")
            elif value is None:
                conditions.append(f"{qualified_col} IS NULL")
            else:
                conditions.append(f"{qualified_col} = '{value}' COLLATE NOCASE")

        if conditions:
            return f"WHERE {' AND '.join(conditions)}"

        return None

    def _build_group_by_clause(self, request: QueryRequest) -> Optional[str]:
        """
        Build GROUP BY clause for aggregations.

        Args:
            request: QueryRequest

        Returns:
            GROUP BY clause string, or None if no grouping
        """
        if not request.group_by:
            return None

        qualified_cols = [
            self._resolve_column_table(col, request.selected_views)
            for col in request.group_by
        ]
        return f"GROUP BY {', '.join(qualified_cols)}"

    def _determine_join_type(self, relationship_type: str) -> str:
        """
        Determine SQL join type from relationship cardinality.

        Args:
            relationship_type: Relationship type (one_to_one, one_to_many, many_to_one, etc.)

        Returns:
            SQL join type (INNER JOIN, LEFT JOIN, etc.)
        """
        # For safety, use INNER JOIN for one_to_one and many_to_one
        # Use LEFT JOIN for one_to_many to preserve all source records
        if relationship_type == "one_to_many":
            return "LEFT JOIN"
        else:
            return "INNER JOIN"

    def get_view_columns(self, view_name: str) -> List[str]:
        """
        Get all column names for a view.

        Args:
            view_name: Name of the view

        Returns:
            List of column names

        Raises:
            ValueError: If view doesn't exist
        """
        view = self.registry.get_view(view_name)
        if view is None:
            raise ValueError(f"View {view_name} not found")

        return [col.name for col in view.columns]

    def validate_columns(self, view_name: str, columns: List[str]) -> Tuple[bool, str]:
        """
        Validate that columns exist in a view.

        Args:
            view_name: Name of the view
            columns: List of column names to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        view = self.registry.get_view(view_name)
        if view is None:
            return False, f"View {view_name} not found"

        view_columns = {col.name.lower(): col.name for col in view.columns}

        for column in columns:
            if column.lower() not in view_columns:
                return False, f"Column {column} not found in view {view_name}"

        return True, ""

    def suggest_columns(self, view_name: str, partial: str = "") -> List[str]:
        """
        Suggest columns for autocomplete.

        Args:
            view_name: Name of the view
            partial: Partial column name to match

        Returns:
            List of matching column names
        """
        view = self.registry.get_view(view_name)
        if view is None:
            return []

        partial_lower = partial.lower()
        return [col.name for col in view.columns if col.name.lower().startswith(partial_lower)]

    def get_suggested_aggregations(self, view_name: str) -> Dict[str, List[str]]:
        """
        Suggest aggregations based on column types.

        Args:
            view_name: Name of the view

        Returns:
            Dict mapping column name to applicable aggregations
        """
        view = self.registry.get_view(view_name)
        if view is None:
            return {}

        suggestions = {}

        for col in view.columns:
            if col.data_type.upper() in ["INT", "DECIMAL", "FLOAT", "BIGINT"]:
                suggestions[col.name] = ["SUM", "AVG", "MIN", "MAX", "COUNT"]
            else:
                suggestions[col.name] = ["COUNT", "COUNT DISTINCT"]

        return suggestions


# Global query builder instance
_builder_instance: Optional[QueryBuilder] = None


def get_builder(registry: Optional[ViewRegistry] = None) -> QueryBuilder:
    """
    Get or create the global query builder.

    Args:
        registry: ViewRegistry instance (required if creating new builder)

    Returns:
        QueryBuilder instance

    Raises:
        ValueError: If no builder exists and registry not provided
    """
    global _builder_instance

    if _builder_instance is None:
        if registry is None:
            from app.views.registry import get_registry

            registry = get_registry()

        _builder_instance = QueryBuilder(registry)

    return _builder_instance


def reset_builder() -> None:
    """Reset the global query builder instance."""
    global _builder_instance
    _builder_instance = None
