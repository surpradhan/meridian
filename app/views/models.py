"""
View Metadata Models

Pydantic models for representing database view metadata, including columns,
view schemas, join relationships, and query requests.

These models provide type-safe, validated metadata that agents can use to
understand the data landscape and construct safe queries.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


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


class QueryRequest(BaseModel):
    """
    Represents a request to query one or more views.

    Used by agents to specify which views to query and how to filter/aggregate.

    Attributes:
        selected_views: List of view names to query
        filters: Optional dict of column filters (WHERE clauses)
        limit: Maximum number of rows to return
        aggregations: Optional dict of column aggregations (SUM, COUNT, etc.)
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

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "selected_views": ["sales_fact", "customer_dim"],
                "filters": {"region": "WEST", "date_year": 2024},
                "limit": 100,
                "aggregations": {"amount": "SUM"},
                "group_by": ["region"],
            }
        }
