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
from typing import List, Set, Dict, Any, Optional, Tuple, Union
from app.views.models import QueryRequest, WindowFunction
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
        Build a SQL query string from a QueryRequest.

        Convenience wrapper around ``build_query_parameterized`` that discards
        the params list and returns only the SQL template string.  The returned
        string contains ``?`` placeholders wherever user-supplied values appear —
        it is **not** a fully inlined query and cannot be executed directly without
        binding parameters.

        Use this method for display, logging, or tests that only need to inspect
        SQL structure.  For production execution use ``build_query_parameterized``
        and pass the returned params to ``db.execute_query``.

        Args:
            request: QueryRequest with selected views, filters, aggregations, etc.

        Returns:
            SQL template string with ``?`` placeholders (params discarded)

        Raises:
            ValueError: If views are invalid or cannot be joined
        """
        sql, _ = self.build_query_parameterized(request)
        return sql

    def build_query_parameterized(self, request: QueryRequest) -> Tuple[str, List[Any]]:
        """
        Build a parameterized SQL query from a QueryRequest.

        All user-supplied string/numeric values in WHERE and HAVING clauses are
        replaced with ``?`` placeholders and returned separately in the params
        list, preventing SQL injection.

        Args:
            request: QueryRequest with selected views, filters, aggregations, etc.

        Returns:
            Tuple of (sql_template, params) ready for ``db.execute_query(sql, params)``

        Raises:
            ValueError: If views are invalid or cannot be joined
        """
        # Resolve time expressions into concrete date-range filters first so
        # the rest of the builder sees them as ordinary filters.
        request = self._apply_time_expression(request)

        # Validate views exist
        views = request.selected_views
        for view in views:
            if self.registry.get_view(view) is None:
                raise ValueError(f"View {view} not found in registry")

        params: List[Any] = []

        # Build CTE preamble (WITH clause) — CTEs contain raw SQL; no parameterization
        cte_clause = self._build_cte_clause(request)

        # Build SELECT clause (including any window functions)
        select_clause = self._build_select_clause(request)

        # Build FROM clause with JOINs (single-hop or multi-hop)
        from_clause = self._build_from_clause(request)

        # Build WHERE clause — populates params list
        where_clause = self._build_where_clause_parameterized(request, params)

        # Build GROUP BY clause
        group_by_clause = self._build_group_by_clause(request)

        # Build HAVING clause — populates params list
        having_clause = self._build_having_clause_parameterized(request, params)

        # Build ORDER BY clause
        order_by_clause = self._build_order_by_clause(request)

        # Build LIMIT clause
        limit_clause = f"LIMIT {request.limit}"

        # Assemble main query body
        parts = [select_clause, from_clause]
        if where_clause:
            parts.append(where_clause)
        if group_by_clause:
            parts.append(group_by_clause)
        if having_clause:
            parts.append(having_clause)
        if order_by_clause:
            parts.append(order_by_clause)
        parts.append(limit_clause)

        main_query = " ".join(parts)

        # Prepend CTE if present
        sql = f"{cte_clause} {main_query}" if cte_clause else main_query
        logger.debug(f"Built query: {sql}  params={params}")

        return sql, params

    def _build_select_clause(self, request: QueryRequest) -> str:
        """
        Build SELECT clause with appropriate columns.

        Handles plain column selection, aggregations, and window functions.

        Args:
            request: QueryRequest

        Returns:
            SELECT clause string
        """
        parts: List[str] = []

        if request.aggregations:
            # Add group-by dimensions first so they appear left of aggregates
            if request.group_by:
                for group_col in request.group_by:
                    qualified_col = self._resolve_column_table(group_col, request.selected_views)
                    parts.append(qualified_col)

            for column, agg_func in request.aggregations.items():
                qualified_col = self._resolve_column_table(column, request.selected_views)
                parts.append(f"{agg_func}({qualified_col}) AS {agg_func}_{column}")
        else:
            # Select all columns from all views
            parts = [f"{view}.*" for view in request.selected_views]

        # Append window functions if any
        if request.window_functions:
            for wf in request.window_functions:
                parts.append(self._render_window_function(wf, request.selected_views, request.aggregations))

        return f"SELECT {', '.join(parts)}"

    def _render_window_function(
        self,
        wf: WindowFunction,
        views: List[str],
        aggregations: Optional[dict] = None,
    ) -> str:
        """Render a WindowFunction spec into a SQL expression with alias.

        The ``arguments`` field is placed verbatim inside the function parentheses,
        allowing functions that require arguments (NTILE, NTH_VALUE, LAG, LEAD) to
        be expressed correctly.  Zero-argument functions (ROW_NUMBER, RANK, SUM, …)
        leave ``arguments`` as None and get empty parentheses.

        ``aggregations`` is used to expand aggregate aliases (e.g. ``SUM_amount``)
        inside the window ORDER BY to their full expressions, since SQLite does not
        allow column aliases in that position.
        """
        func = wf.function.upper()
        func_args = wf.arguments or ""

        # Build alias → full-expression map so window ORDER BY can dereference them.
        # e.g. {"SUM_amount": "SUM(sales_fact.amount)"}
        agg_expr_map: dict = {}
        if aggregations:
            for col, agg_func in aggregations.items():
                alias = f"{agg_func}_{col}"
                qualified_col = self._resolve_column_table(col, views)
                agg_expr_map[alias] = f"{agg_func}({qualified_col})"

        # PARTITION BY
        if wf.partition_by:
            qualified_parts = [
                self._resolve_column_table(col, views) for col in wf.partition_by
            ]
            partition_clause = f"PARTITION BY {', '.join(qualified_parts)}"
        else:
            partition_clause = ""

        # ORDER BY inside window — expand aggregate aliases to full expressions so
        # SQLite (which disallows alias references in window ORDER BY) doesn't error.
        if wf.order_by:
            ob_parts = []
            for item in wf.order_by:
                if item.column in agg_expr_map:
                    col_expr = agg_expr_map[item.column]
                else:
                    col_expr = self._resolve_column_table(item.column, views)
                ob_parts.append(f"{col_expr} {item.direction}")
            order_clause = f"ORDER BY {', '.join(ob_parts)}"
        else:
            order_clause = ""

        window_spec_parts = [p for p in [partition_clause, order_clause] if p]
        window_spec = " ".join(window_spec_parts)

        return f"{func}({func_args}) OVER ({window_spec}) AS {wf.alias}"

    def _build_from_clause(self, request: QueryRequest) -> str:
        """
        Build FROM clause with automatic JOINs (single-hop and multi-hop).

        Joins multiple views using the registry. When two requested views have
        no direct relationship, the shortest join path through intermediate views
        is found automatically and those bridge views are injected into the JOIN
        chain — enabling true multi-hop queries.

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

        # Track which views have already been emitted in the JOIN chain so we
        # never JOIN the same view twice (even if it appears on multiple paths).
        emitted: Set[str] = {views[0]}
        from_parts = [f"FROM {views[0]}"]

        for i in range(1, len(views)):
            target_view = views[i]

            if target_view in emitted:
                # Already in the chain — skip (happens when an intermediate view
                # was injected for an earlier hop)
                continue

            # Try a direct join from any already-emitted view
            join_rel = None
            anchor_view = None
            for emitted_view in reversed(list(emitted)):
                join_rel = self.registry.find_joins(emitted_view, target_view)
                if join_rel:
                    anchor_view = emitted_view
                    break
                join_rel = self.registry.find_joins(target_view, emitted_view)
                if join_rel:
                    anchor_view = emitted_view
                    break

            if join_rel is not None:
                # Direct join found
                join_type = self._determine_join_type(join_rel.relationship_type)
                from_parts.append(f"{join_type} {target_view} ON {join_rel.get_join_condition()}")
                emitted.add(target_view)
            else:
                # No direct join — try multi-hop pathfinding from any emitted view
                path = None
                for emitted_view in reversed(list(emitted)):
                    path = self.registry.find_join_path(emitted_view, target_view)
                    if path:
                        break

                if path is None:
                    raise ValueError(
                        f"No join path found from any joined view to '{target_view}'"
                    )

                # Walk the path and emit JOIN for each step not yet in the chain
                for step_idx in range(1, len(path)):
                    step_view = path[step_idx]
                    prev_view = path[step_idx - 1]

                    if step_view in emitted:
                        continue

                    rel = self.registry.find_joins(prev_view, step_view) or \
                          self.registry.find_joins(step_view, prev_view)

                    if rel is None:
                        raise ValueError(
                            f"Expected join between '{prev_view}' and '{step_view}' "
                            "but none found in registry"
                        )

                    join_type = self._determine_join_type(rel.relationship_type)
                    from_parts.append(f"{join_type} {step_view} ON {rel.get_join_condition()}")
                    emitted.add(step_view)

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
        Build WHERE clause with values inlined as literals.

        Kept for backward-compatible ``build_query`` (display/logging only).
        Production execution should use ``_build_where_clause_parameterized``.
        """
        params: List[Any] = []
        return self._build_where_clause_parameterized(request, params, inline=True)

    def _build_where_clause_parameterized(
        self,
        request: QueryRequest,
        params: List[Any],
        inline: bool = False,
    ) -> Optional[str]:
        """
        Build WHERE clause from filters.

        Regular filters are key→value pairs. Range filters produced by time
        intelligence use the ``__gte__<col>`` / ``__lte__<col>`` prefix convention.

        When ``inline=False`` (default, production path), string/numeric values are
        replaced with ``?`` placeholders and appended to ``params``.
        When ``inline=True`` (display/logging path), values are embedded as literals.

        Args:
            request: QueryRequest
            params: List to append bound parameter values to (mutated in place)
            inline: If True, inline values as literals instead of placeholders

        Returns:
            WHERE clause string, or None if no filters
        """
        if not request.filters:
            return None

        conditions = []
        for column, value in request.filters.items():
            # Date-range operators injected by time intelligence
            if column.startswith("__gte__"):
                real_col = column[len("__gte__"):]
                qualified_col = self._resolve_column_table(real_col, request.selected_views)
                if inline:
                    conditions.append(f"{qualified_col} >= '{value}'")
                else:
                    conditions.append(f"{qualified_col} >= ?")
                    params.append(value)
                continue
            if column.startswith("__lte__"):
                real_col = column[len("__lte__"):]
                qualified_col = self._resolve_column_table(real_col, request.selected_views)
                if inline:
                    conditions.append(f"{qualified_col} <= '{value}'")
                else:
                    conditions.append(f"{qualified_col} <= ?")
                    params.append(value)
                continue

            qualified_col = self._resolve_column_table(column, request.selected_views)
            if value is None:
                conditions.append(f"{qualified_col} IS NULL")
            elif inline:
                if isinstance(value, (int, float)):
                    conditions.append(f"{qualified_col} = {value}")
                else:
                    escaped = str(value).replace("'", "''")
                    conditions.append(f"{qualified_col} = '{escaped}' COLLATE NOCASE")
            else:
                if isinstance(value, (int, float)):
                    conditions.append(f"{qualified_col} = ?")
                    params.append(value)
                else:
                    conditions.append(f"{qualified_col} = ? COLLATE NOCASE")
                    params.append(str(value))

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

    _SAFE_HAVING_OPS = frozenset({"=", "!=", "<>", ">", ">=", "<", "<="})

    def _build_having_clause(self, request: QueryRequest) -> Optional[str]:
        """
        Build HAVING clause with values inlined as literals.

        Kept for backward-compatible ``build_query`` (display/logging only).
        Production execution should use ``_build_having_clause_parameterized``.
        """
        params: List[Any] = []
        return self._build_having_clause_parameterized(request, params, inline=True)

    def _build_having_clause_parameterized(
        self,
        request: QueryRequest,
        params: List[Any],
        inline: bool = False,
    ) -> Optional[str]:
        """
        Build HAVING clause for aggregate filters.

        Each key in ``request.having`` is ``<AGG>_<column>`` and the value is a
        dict with ``op`` (comparison operator, whitelisted) and ``value``
        (must be numeric — strings are rejected to prevent injection).

        Example::
            having={"SUM_amount": {"op": ">", "value": 10000}}
            → HAVING SUM(sales_fact.amount) > ?   (params=[10000])

        Args:
            request: QueryRequest
            params: List to append bound values to (mutated in place)
            inline: If True, inline values as literals instead of placeholders

        Returns:
            HAVING clause string, or None if no having conditions

        Raises:
            ValueError: If a HAVING value is not numeric, or the operator is
                        not in the allowed set.
        """
        if not request.having or not request.aggregations:
            return None

        conditions = []
        for alias_key, condition in request.having.items():
            # alias_key format: "<AGG>_<column>" (e.g. "SUM_amount")
            key_parts = alias_key.split("_", 1)
            if len(key_parts) != 2:
                raise ValueError(
                    f"HAVING key '{alias_key}' is malformed. "
                    "Expected '<AGG>_<column>' (e.g. 'SUM_amount')."
                )
            agg_func, column = key_parts[0].upper(), key_parts[1]
            qualified_col = self._resolve_column_table(column, request.selected_views)

            op = condition.get("op", ">")
            if op not in self._SAFE_HAVING_OPS:
                raise ValueError(
                    f"HAVING operator '{op}' is not allowed. "
                    f"Permitted: {', '.join(sorted(self._SAFE_HAVING_OPS))}"
                )

            val = condition.get("value", 0)
            if not isinstance(val, (int, float)):
                raise ValueError(
                    f"HAVING value for '{alias_key}' must be numeric, got {type(val).__name__!r}. "
                    "Use aggregation filters only on numeric columns."
                )

            if inline:
                conditions.append(f"{agg_func}({qualified_col}) {op} {val}")
            else:
                conditions.append(f"{agg_func}({qualified_col}) {op} ?")
                params.append(val)

        if conditions:
            return f"HAVING {' AND '.join(conditions)}"
        return None

    def _build_order_by_clause(self, request: QueryRequest) -> Optional[str]:
        """
        Build ORDER BY clause.

        Each entry in ``request.order_by`` is a dict with ``column`` and
        optional ``direction`` (ASC/DESC, defaults to ASC).

        Args:
            request: QueryRequest

        Returns:
            ORDER BY clause string, or None if no ordering specified
        """
        if not request.order_by:
            return None

        # Build the exact set of aggregate alias names used in the SELECT clause
        # (e.g. {"SUM_amount", "COUNT_sale_id"}) so we can match precisely instead
        # of relying on a fragile string-prefix heuristic that would mis-classify
        # real column names like "sum_of_debits".
        agg_aliases: Set[str] = set()
        if request.aggregations:
            for agg_col, agg_func in request.aggregations.items():
                agg_aliases.add(f"{agg_func}_{agg_col}")

        parts = []
        for item in request.order_by:
            col = item.column
            direction = item.direction
            if col in agg_aliases:
                # Aggregate alias — emit as-is (already the right expression)
                parts.append(f"{col} {direction}")
            else:
                qualified = self._resolve_column_table(col, request.selected_views)
                parts.append(f"{qualified} {direction}")

        if parts:
            return f"ORDER BY {', '.join(parts)}"
        return None

    def _build_cte_clause(self, request: QueryRequest) -> Optional[str]:
        """
        Build WITH (CTE) preamble.

        .. warning:: **Trust boundary** — ``CTEDefinition.sql`` is embedded verbatim.
            CTEs are never user-typed input; they are either LLM-generated (already
            sandboxed by the view-schema prompt) or constructed in code.  Do **not**
            accept raw CTE SQL from untrusted external sources without validation.

        Args:
            request: QueryRequest

        Returns:
            ``WITH name AS (sql), ...`` string, or None if no CTEs
        """
        if not request.ctes:
            return None

        cte_parts = [f"{cte.name} AS ({cte.sql})" for cte in request.ctes]
        return f"WITH {', '.join(cte_parts)}"

    def _apply_time_expression(self, request: QueryRequest) -> QueryRequest:
        """
        Resolve ``request.time_expression`` into concrete date-range filters
        and merge them into ``request.filters``.

        Validates that ``time_column`` exists in at least one of the selected
        views before emitting a filter, so unrecognised column names are caught
        here with a clear error rather than propagating as unqualified SQL.

        Args:
            request: QueryRequest (copied via model_copy, never mutated in place)

        Returns:
            Updated QueryRequest with filters populated and time fields cleared.

        Raises:
            ValueError: If time_column is not found in any selected view.
        """
        if not request.time_expression or not request.time_column:
            return request

        # Validate the column exists in at least one of the queried views
        col_lower = request.time_column.lower()
        found = False
        for view_name in request.selected_views:
            view = self.registry.get_view(view_name)
            if view and any(c.name.lower() == col_lower for c in view.columns):
                found = True
                break
        if not found:
            raise ValueError(
                f"time_column '{request.time_column}' not found in any of the selected views: "
                f"{request.selected_views}"
            )

        from app.query.time_intelligence import build_date_filters

        date_filters = build_date_filters(request.time_expression, request.time_column)
        if date_filters is None:
            logger.warning(
                f"Could not resolve time expression '{request.time_expression}'; ignoring"
            )
            return request

        merged_filters = dict(request.filters or {})
        merged_filters.update(date_filters)

        return request.model_copy(
            update={
                "filters": merged_filters,
                "time_expression": None,
                "time_column": None,
            }
        )

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
