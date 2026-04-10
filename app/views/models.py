"""
View Metadata Models

Pydantic models for representing database view metadata, including columns,
view schemas, join relationships, and query requests.

These models provide type-safe, validated metadata that agents can use to
understand the data landscape and construct safe queries.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator


class ColumnSchema(BaseModel):
    """
    Represents a single column/field in a database view.

    Attributes:
        name: Column name
        data_type: SQL data type (VARCHAR, INT, DECIMAL, DATE, BOOLEAN, etc.)
        is_nullable: Whether column accepts NULL values
        description: Human-readable description of what this column contains
        is_primary_key: Whether this column is a primary key
        is_foreign_key: Whether this column is a foreign key
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Column name",
    )
    data_type: str = Field(
        ...,
        description="SQL data type (VARCHAR, INT, DECIMAL, DATE, TIMESTAMP, BOOLEAN, etc.)",
    )
    is_nullable: bool = Field(
        default=True,
        description="Whether the column accepts NULL values",
    )
    description: str = Field(
        default="",
        description="Human-readable description of the column",
    )
    is_primary_key: bool = Field(
        default=False,
        description="Whether this is a primary key column",
    )
    is_foreign_key: bool = Field(
        default=False,
        description="Whether this is a foreign key column",
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "name": "customer_id",
                "data_type": "INT",
                "is_nullable": False,
                "description": "Unique identifier for customer",
                "is_primary_key": True,
                "is_foreign_key": False,
            }
        }


class ViewSchema(BaseModel):
    """
    Represents a complete database view/table with all its metadata.

    Attributes:
        name: View name (can include schema prefix like "public.sales_fact")
        view_type: Type of view - "fact" for transaction tables, "dimension" for master data
        description: Human-readable description of the view's purpose
        domain: Business domain (sales, finance, operations, etc.)
        columns: List of all columns in this view
        row_count: Optional estimate of rows in this view
    """

    name: str = Field(
        ...,
        min_length=1,
        description="View or table name",
    )
    view_type: Literal["fact", "dimension"] = Field(
        ...,
        description="Type of view: 'fact' for transaction tables, 'dimension' for master data",
    )
    description: str = Field(
        default="",
        description="Purpose and content of this view",
    )
    domain: str = Field(
        ...,
        min_length=1,
        description="Business domain (sales, finance, operations, etc.)",
    )
    columns: List[ColumnSchema] = Field(
        ...,
        min_items=1,
        description="All columns available in this view",
    )
    row_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Approximate number of rows (for query optimization)",
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "name": "sales_fact",
                "view_type": "fact",
                "description": "Daily sales transactions with amounts and quantities",
                "domain": "sales",
                "columns": [
                    {
                        "name": "sale_id",
                        "data_type": "INT",
                        "is_nullable": False,
                        "description": "Unique sale identifier",
                        "is_primary_key": True,
                        "is_foreign_key": False,
                    }
                ],
                "row_count": 1000000,
            }
        }

    def get_column(self, column_name: str) -> Optional[ColumnSchema]:
        """Get a column by name.

        Args:
            column_name: Name of the column to find

        Returns:
            ColumnSchema if found, None otherwise
        """
        for col in self.columns:
            if col.name.lower() == column_name.lower():
                return col
        return None

    def get_primary_keys(self) -> List[str]:
        """Get all primary key column names.

        Returns:
            List of primary key column names
        """
        return [col.name for col in self.columns if col.is_primary_key]

    def get_foreign_keys(self) -> List[str]:
        """Get all foreign key column names.

        Returns:
            List of foreign key column names
        """
        return [col.name for col in self.columns if col.is_foreign_key]


class JoinRelationship(BaseModel):
    """
    Represents a join relationship between two views.

    Defines how two views can be joined together, including the join keys
    and the relationship cardinality.

    Attributes:
        source_view: Name of the source view
        target_view: Name of the target view to join to
        source_columns: Columns from source view to use in join
        target_columns: Columns from target view to use in join (must match source_columns length)
        relationship_type: Cardinality of the relationship
        description: Human-readable description of this join
    """

    source_view: str = Field(
        ...,
        min_length=1,
        description="Source view name",
    )
    target_view: str = Field(
        ...,
        min_length=1,
        description="Target view name to join",
    )
    source_columns: List[str] = Field(
        ...,
        min_items=1,
        description="Join columns from source view",
    )
    target_columns: List[str] = Field(
        ...,
        min_items=1,
        description="Join columns from target view",
    )
    relationship_type: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] = Field(
        ...,
        description="Cardinality of the join relationship",
    )
    description: str = Field(
        default="",
        description="Description of why/how these views are related",
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "source_view": "sales_fact",
                "target_view": "customer_dim",
                "source_columns": ["customer_id"],
                "target_columns": ["customer_id"],
                "relationship_type": "many_to_one",
                "description": "Each sale belongs to one customer",
            }
        }

    def validate(self) -> tuple[bool, str]:
        """
        Validate the join relationship.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(self.source_columns) != len(self.target_columns):
            return False, "source_columns and target_columns must have same length"

        if self.source_view == self.target_view:
            return False, "Cannot join view to itself"

        return True, ""

    def get_join_condition(self) -> str:
        """
        Generate SQL join condition string.

        Returns:
            SQL ON clause condition (e.g., "source.id = target.id")
        """
        conditions = []
        for src_col, tgt_col in zip(self.source_columns, self.target_columns):
            conditions.append(f"{self.source_view}.{src_col} = {self.target_view}.{tgt_col}")
        return " AND ".join(conditions)


_VALID_WINDOW_FUNCTIONS = {
    "ROW_NUMBER", "RANK", "DENSE_RANK",
    "LAG", "LEAD",
    "SUM", "AVG", "COUNT", "MIN", "MAX",
    "FIRST_VALUE", "LAST_VALUE", "NTH_VALUE",
    "NTILE", "CUME_DIST", "PERCENT_RANK",
}


class OrderByItem(BaseModel):
    """A single ORDER BY column + direction specification."""

    column: str = Field(..., min_length=1, description="Column name to order by")
    direction: Literal["ASC", "DESC"] = Field(default="ASC", description="Sort direction")


class WindowFunction(BaseModel):
    """
    Defines a window function to include in the SELECT clause.

    Attributes:
        alias: Column alias for the window function result
        function: Window function name — must be one of the supported SQL window functions
        arguments: Optional raw argument string placed inside the function call parentheses.
            Required for functions that take arguments: ``NTILE(4)``, ``NTH_VALUE(col, 2)``,
            ``LAG(col, 1)``, ``LEAD(col, 1)``.  Leave ``None`` for zero-argument functions
            like ``ROW_NUMBER``, ``RANK``, ``DENSE_RANK``, ``SUM``, etc.
        partition_by: Columns to partition by (PARTITION BY clause)
        order_by: Columns + direction for ORDER BY inside the window
    """

    alias: str = Field(..., min_length=1, description="Alias for the computed column")
    function: str = Field(..., description="Window function (ROW_NUMBER, RANK, SUM, etc.)")
    arguments: Optional[str] = Field(
        default=None,
        description=(
            "Arguments placed inside the function parentheses — required for "
            "NTILE(n), NTH_VALUE(col, n), LAG(col, offset), LEAD(col, offset). "
            "Leave None for zero-argument functions (ROW_NUMBER, RANK, SUM, …)."
        ),
    )
    partition_by: Optional[List[str]] = Field(default=None, description="PARTITION BY columns")
    order_by: Optional[List[OrderByItem]] = Field(
        default=None,
        description="ORDER BY inside window",
    )

    @validator("function")
    @classmethod
    def function_must_be_valid(cls, v: str) -> str:
        normalised = v.strip().upper()
        if normalised not in _VALID_WINDOW_FUNCTIONS:
            raise ValueError(
                f"Invalid window function '{v}'. "
                f"Must be one of: {', '.join(sorted(_VALID_WINDOW_FUNCTIONS))}"
            )
        return normalised


class CTEDefinition(BaseModel):
    """
    A Common Table Expression (WITH clause) definition.

    Attributes:
        name: CTE name used in the main query
        sql: Raw SQL for the CTE body (SELECT ...)
    """

    name: str = Field(..., description="CTE name referenced in the main query")
    sql: str = Field(..., description="SQL body for the CTE (without the name AS ( ) wrapper)")


class QueryRequest(BaseModel):
    """
    Represents a request to query one or more views.

    Used by agents to specify which views to query and how to filter/aggregate.

    Attributes:
        selected_views: List of view names to query
        filters: Optional dict of column filters (WHERE clauses)
        limit: Maximum number of rows to return
        aggregations: Optional dict of column aggregations (SUM, COUNT, etc.)
        group_by: Columns to GROUP BY
        having: Aggregate filters (HAVING clause), keyed by "AGG_column"
        order_by: ORDER BY columns and directions
        window_functions: Window functions to add to the SELECT clause
        ctes: Common Table Expressions (WITH clauses)
        time_expression: Temporal expression to resolve (e.g. "last_quarter")
        time_column: Column to apply the time_expression filter to
    """

    selected_views: List[str] = Field(
        ...,
        min_items=1,
        description="Views to query",
    )
    filters: Optional[dict] = Field(
        default=None,
        description="Filters to apply (WHERE clauses) as key-value pairs",
    )
    limit: int = Field(
        default=100,
        ge=1,
        description="Maximum rows to return",
    )
    aggregations: Optional[dict] = Field(
        default=None,
        description="Aggregations to apply (e.g., {'amount': 'SUM', 'id': 'COUNT'})",
    )
    group_by: Optional[List[str]] = Field(
        default=None,
        description="Columns to group by",
    )
    having: Optional[dict] = Field(
        default=None,
        description=(
            "HAVING conditions on aggregated columns. "
            "Keys are '<AGG>_<column>' (e.g. 'SUM_amount'), "
            "values are dicts with 'op' (e.g. '>') and 'value'."
        ),
    )
    order_by: Optional[List[OrderByItem]] = Field(
        default=None,
        description="ORDER BY columns and directions",
    )
    window_functions: Optional[List[WindowFunction]] = Field(
        default=None,
        description="Window functions to add to the SELECT clause",
    )
    ctes: Optional[List[CTEDefinition]] = Field(
        default=None,
        description="Common Table Expressions (WITH clauses) prepended to the query",
    )
    time_expression: Optional[str] = Field(
        default=None,
        description="Temporal expression to resolve (e.g. 'last_quarter', 'ytd', 'trailing_30_days')",
    )
    time_column: Optional[str] = Field(
        default=None,
        description="Column name to apply the time_expression filter to (e.g. 'date', 'sale_date')",
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "selected_views": ["sales_fact", "customer_dim"],
                "filters": {"region": "WEST"},
                "limit": 100,
                "aggregations": {"amount": "SUM"},
                "group_by": ["region"],
                "having": {"SUM_amount": {"op": ">", "value": 10000}},
                "order_by": [{"column": "SUM_amount", "direction": "DESC"}],
                "window_functions": [
                    {
                        "alias": "rank",
                        "function": "ROW_NUMBER",
                        "partition_by": ["region"],
                        "order_by": [{"column": "amount", "direction": "DESC"}],
                    }
                ],
                "ctes": [{"name": "top_customers", "sql": "SELECT customer_id FROM sales_fact GROUP BY customer_id ORDER BY SUM(amount) DESC LIMIT 5"}],
                "time_expression": "last_quarter",
                "time_column": "date",
            }
        }
