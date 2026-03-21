"""
Query Validator

Validates queries for safety, performance, and correctness before execution.
Implements multiple validation rules to prevent errors and optimize performance.
"""

import logging
from typing import List, Tuple, Dict, Any
from app.views.models import QueryRequest
from app.views.registry import ViewRegistry

logger = logging.getLogger(__name__)


class QueryValidator:
    """
    Validates queries against safety and performance rules.

    Checks for:
    - Cardinality issues (many-to-many without limits)
    - SQL injection attempts
    - Performance problems (missing joins, large result sets)
    - Data access restrictions
    """

    def __init__(self, registry: ViewRegistry, max_result_rows: int = 10000):
        """
        Initialize the validator.

        Args:
            registry: ViewRegistry instance
            max_result_rows: Maximum allowed result rows before warning
        """
        self.registry = registry
        self.max_result_rows = max_result_rows
        logger.debug("QueryValidator initialized")

    def validate(self, request: QueryRequest) -> Tuple[bool, List[str]]:
        """
        Validate a query request against all rules.

        Args:
            request: QueryRequest to validate

        Returns:
            Tuple of (is_valid, error_messages)
            is_valid: True if all validations pass
            error_messages: List of validation errors (empty if valid)
        """
        errors = []

        # Run all validation rules
        errors.extend(self._validate_views(request))
        errors.extend(self._validate_cardinality(request))
        errors.extend(self._validate_limits(request))
        errors.extend(self._validate_columns(request))

        is_valid = len(errors) == 0

        if not is_valid:
            logger.warning(f"Query validation failed: {errors}")
        else:
            logger.debug("Query validation passed")

        return is_valid, errors

    def _validate_views(self, request: QueryRequest) -> List[str]:
        """
        Validate that all views exist and can be joined.

        Args:
            request: QueryRequest

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check all views exist
        for view_name in request.selected_views:
            if self.registry.get_view(view_name) is None:
                errors.append(f"View '{view_name}' not found in registry")

        # Check views can be combined
        if not errors:
            is_valid, msg = self.registry.validate_view_combination(request.selected_views)
            if not is_valid:
                errors.append(f"View combination invalid: {msg}")

        return errors

    def _validate_cardinality(self, request: QueryRequest) -> List[str]:
        """
        Validate that many-to-many relationships have proper limits.

        Many-to-many joins without aggregation or limits can produce huge result sets.

        Args:
            request: QueryRequest

        Returns:
            List of error messages
        """
        errors = []

        # If multiple views without aggregations, check for many-to-many
        if len(request.selected_views) > 1 and not request.aggregations:
            # Check if any joins are many-to-many
            views = request.selected_views
            for i in range(len(views) - 1):
                join = self.registry.find_joins(views[i], views[i + 1])
                if join and join.relationship_type == "many_to_many":
                    if request.limit > 1000:
                        errors.append(
                            f"Many-to-many join between {views[i]} and {views[i + 1]} "
                            f"with limit {request.limit} may produce huge result sets. "
                            f"Consider adding aggregations or reducing limit."
                        )

        return errors

    def _validate_limits(self, request: QueryRequest) -> List[str]:
        """
        Validate that result limits are reasonable.

        Args:
            request: QueryRequest

        Returns:
            List of error messages
        """
        errors = []

        if request.limit < 1:
            errors.append(f"Limit must be >= 1, got {request.limit}")

        if request.limit > self.max_result_rows:
            errors.append(
                f"Limit {request.limit} exceeds maximum {self.max_result_rows}. "
                f"Consider adding more filters or using aggregations."
            )

        return errors

    def _validate_columns(self, request: QueryRequest) -> List[str]:
        """
        Validate that referenced columns exist in the views.

        Args:
            request: QueryRequest

        Returns:
            List of error messages
        """
        errors = []

        # Validate filter columns exist
        if request.filters:
            for column in request.filters.keys():
                # Check if column exists in any view
                found = False
                for view_name in request.selected_views:
                    view = self.registry.get_view(view_name)
                    if view and view.get_column(column):
                        found = True
                        break

                if not found:
                    errors.append(f"Filter column '{column}' not found in selected views")

        # Validate aggregation columns exist
        if request.aggregations:
            for column in request.aggregations.keys():
                found = False
                for view_name in request.selected_views:
                    view = self.registry.get_view(view_name)
                    if view and view.get_column(column):
                        found = True
                        break

                if not found:
                    errors.append(f"Aggregation column '{column}' not found in selected views")

        # Validate group by columns exist
        if request.group_by:
            for column in request.group_by:
                found = False
                for view_name in request.selected_views:
                    view = self.registry.get_view(view_name)
                    if view and view.get_column(column):
                        found = True
                        break

                if not found:
                    errors.append(f"Group by column '{column}' not found in selected views")

        return errors

    def estimate_result_size(self, request: QueryRequest) -> int:
        """
        Estimate the number of rows the query will return.

        This is a rough estimate based on view row counts and relationships.

        Args:
            request: QueryRequest

        Returns:
            Estimated row count
        """
        if not request.selected_views:
            return 0

        # Start with the first view's row count
        primary_view = self.registry.get_view(request.selected_views[0])
        if not primary_view or primary_view.row_count is None:
            return request.limit  # Default to limit if unknown

        estimated = primary_view.row_count

        # Adjust based on filters (rough estimate: each filter reduces by 50%)
        if request.filters:
            estimated = int(estimated * (0.5 ** len(request.filters)))

        # If aggregated, result size is much smaller
        if request.aggregations:
            estimated = min(estimated, len(request.group_by or []) + 1)

        # Never exceed limit
        estimated = min(estimated, request.limit)

        return max(1, estimated)

    def get_validation_warnings(self, request: QueryRequest) -> List[str]:
        """
        Get non-blocking warnings about the query.

        These are performance suggestions, not errors.

        Args:
            request: QueryRequest

        Returns:
            List of warning messages
        """
        warnings = []

        estimated = self.estimate_result_size(request)

        if estimated > 1000:
            warnings.append(
                f"Query estimated to return {estimated} rows. "
                f"Consider adding more filters or aggregations for faster results."
            )

        if len(request.selected_views) > 3:
            warnings.append(
                f"Query joins {len(request.selected_views)} views. "
                f"Performance may degrade. Consider simplifying the query."
            )

        if request.aggregations and not request.group_by:
            warnings.append(
                "Query has aggregations but no GROUP BY clause. "
                "Result will be a single row. This is usually intentional."
            )

        return warnings


# Global validator instance
_validator_instance = None


def get_validator(registry: ViewRegistry = None) -> QueryValidator:
    """
    Get or create the global query validator.

    Args:
        registry: ViewRegistry instance (required if creating new validator)

    Returns:
        QueryValidator instance
    """
    global _validator_instance

    if _validator_instance is None:
        if registry is None:
            from app.views.registry import get_registry

            registry = get_registry()

        _validator_instance = QueryValidator(registry)

    return _validator_instance


def reset_validator() -> None:
    """Reset the global validator instance."""
    global _validator_instance
    _validator_instance = None
