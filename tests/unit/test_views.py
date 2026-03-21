"""
Unit Tests for View Registry

Tests the view metadata models, registry functionality, and relationships.
Verifies that agents can discover and validate views correctly.
"""

import pytest
from app.views.models import ColumnSchema, ViewSchema, JoinRelationship, QueryRequest
from app.views.registry import ViewRegistry, create_test_registry


class TestColumnSchema:
    """Test ColumnSchema model validation and functionality."""

    def test_create_valid_column(self):
        """Test creating a valid column schema."""
        col = ColumnSchema(
            name="customer_id",
            data_type="INT",
            is_nullable=False,
            description="Customer identifier",
            is_primary_key=True,
        )
        assert col.name == "customer_id"
        assert col.data_type == "INT"
        assert col.is_primary_key is True

    def test_column_with_defaults(self):
        """Test column creation with default values."""
        col = ColumnSchema(name="amount", data_type="DECIMAL(10,2)")
        assert col.is_nullable is True
        assert col.is_primary_key is False
        assert col.description == ""

    def test_column_validation_invalid_name(self):
        """Test that empty name is rejected."""
        with pytest.raises(Exception):  # Pydantic validation error
            ColumnSchema(name="", data_type="INT")


class TestViewSchema:
    """Test ViewSchema model validation and functionality."""

    def test_create_valid_view(self):
        """Test creating a valid view schema."""
        columns = [
            ColumnSchema(
                name="sale_id", data_type="INT", is_nullable=False, is_primary_key=True
            ),
            ColumnSchema(name="amount", data_type="DECIMAL(10,2)", is_nullable=False),
        ]
        view = ViewSchema(
            name="sales_fact",
            view_type="fact",
            domain="sales",
            description="Sales transactions",
            columns=columns,
        )
        assert view.name == "sales_fact"
        assert view.view_type == "fact"
        assert len(view.columns) == 2

    def test_view_requires_columns(self):
        """Test that view requires at least one column."""
        with pytest.raises(Exception):  # Pydantic validation error
            ViewSchema(
                name="test",
                view_type="fact",
                domain="sales",
                columns=[],  # Empty columns not allowed
            )

    def test_get_column(self):
        """Test getting a column by name."""
        columns = [
            ColumnSchema(name="id", data_type="INT", is_primary_key=True),
            ColumnSchema(name="name", data_type="VARCHAR(255)"),
        ]
        view = ViewSchema(
            name="test_view", view_type="dimension", domain="test", columns=columns
        )

        col = view.get_column("id")
        assert col is not None
        assert col.name == "id"

        col = view.get_column("nonexistent")
        assert col is None

    def test_get_primary_keys(self):
        """Test getting all primary key columns."""
        columns = [
            ColumnSchema(name="id1", data_type="INT", is_primary_key=True),
            ColumnSchema(name="id2", data_type="INT", is_primary_key=True),
            ColumnSchema(name="value", data_type="VARCHAR"),
        ]
        view = ViewSchema(
            name="test", view_type="fact", domain="test", columns=columns
        )

        pks = view.get_primary_keys()
        assert len(pks) == 2
        assert "id1" in pks
        assert "id2" in pks

    def test_get_foreign_keys(self):
        """Test getting all foreign key columns."""
        columns = [
            ColumnSchema(name="id", data_type="INT", is_primary_key=True),
            ColumnSchema(name="fk1", data_type="INT", is_foreign_key=True),
            ColumnSchema(name="fk2", data_type="INT", is_foreign_key=True),
        ]
        view = ViewSchema(
            name="test", view_type="fact", domain="test", columns=columns
        )

        fks = view.get_foreign_keys()
        assert len(fks) == 2
        assert "fk1" in fks
        assert "fk2" in fks


class TestJoinRelationship:
    """Test JoinRelationship model and validation."""

    def test_create_valid_join(self):
        """Test creating a valid join relationship."""
        join = JoinRelationship(
            source_view="sales_fact",
            target_view="customer_dim",
            source_columns=["customer_id"],
            target_columns=["customer_id"],
            relationship_type="many_to_one",
            description="Link to customer",
        )
        assert join.source_view == "sales_fact"
        assert join.target_view == "customer_dim"

    def test_join_validation_mismatched_columns(self):
        """Test that mismatched column counts are rejected."""
        join = JoinRelationship(
            source_view="view1",
            target_view="view2",
            source_columns=["a", "b"],
            target_columns=["x"],  # Mismatch
            relationship_type="many_to_one",
        )
        is_valid, msg = join.validate()
        assert not is_valid
        assert "same length" in msg

    def test_join_validation_self_join(self):
        """Test that self-joins are rejected."""
        join = JoinRelationship(
            source_view="view1",
            target_view="view1",  # Same as source
            source_columns=["a"],
            target_columns=["b"],
            relationship_type="many_to_one",
        )
        is_valid, msg = join.validate()
        assert not is_valid
        assert "itself" in msg

    def test_get_join_condition(self):
        """Test SQL join condition generation."""
        join = JoinRelationship(
            source_view="sales",
            target_view="customers",
            source_columns=["customer_id"],
            target_columns=["id"],
            relationship_type="many_to_one",
        )
        condition = join.get_join_condition()
        assert "sales.customer_id = customers.id" in condition

    def test_get_join_condition_composite(self):
        """Test SQL join condition for composite keys."""
        join = JoinRelationship(
            source_view="sales",
            target_view="customers",
            source_columns=["cust_id", "cust_region"],
            target_columns=["id", "region"],
            relationship_type="many_to_one",
        )
        condition = join.get_join_condition()
        assert "sales.cust_id = customers.id" in condition
        assert "sales.cust_region = customers.region" in condition


class TestViewRegistry:
    """Test ViewRegistry functionality."""

    @pytest.fixture
    def registry(self):
        """Create a test registry with sample data."""
        return create_test_registry()

    def test_registry_creation(self):
        """Test creating an empty registry."""
        reg = ViewRegistry()
        assert len(reg.get_all_views()) == 0
        assert len(reg.get_all_joins()) == 0

    def test_register_view(self, registry):
        """Test registering views."""
        views = registry.get_all_views()
        assert len(views) > 0  # Should have seed data

        # Check specific views
        sales_fact = registry.get_view("sales_fact")
        assert sales_fact is not None
        assert sales_fact.view_type == "fact"
        assert sales_fact.domain == "sales"

    def test_get_view_nonexistent(self, registry):
        """Test getting a nonexistent view."""
        view = registry.get_view("nonexistent_view")
        assert view is None

    def test_get_all_views(self, registry):
        """Test retrieving all views."""
        views = registry.get_all_views()
        assert len(views) >= 8  # At least 8 sample views
        view_names = [v.name for v in views]
        assert "sales_fact" in view_names
        assert "customer_dim" in view_names
        assert "ledger_fact" in view_names

    def test_get_views_by_domain(self, registry):
        """Test filtering views by domain."""
        sales_views = registry.get_views_by_domain("sales")
        assert len(sales_views) == 3  # sales_fact, customer_dim, product_dim
        assert all(v.domain == "sales" for v in sales_views)

        finance_views = registry.get_views_by_domain("finance")
        assert len(finance_views) == 2  # ledger_fact, account_dim

    def test_get_all_domains(self, registry):
        """Test getting all registered domains."""
        domains = registry.get_all_domains()
        assert "sales" in domains
        assert "finance" in domains
        assert "operations" in domains

    def test_find_joins(self, registry):
        """Test finding join relationships."""
        join = registry.find_joins("sales_fact", "customer_dim")
        assert join is not None
        assert join.relationship_type == "many_to_one"

        # Nonexistent join
        join = registry.find_joins("sales_fact", "nonexistent")
        assert join is None

    def test_get_all_joins(self, registry):
        """Test retrieving all joins."""
        joins = registry.get_all_joins()
        assert len(joins) >= 7  # At least 7 sample joins

    def test_validate_view_combination_single(self, registry):
        """Test validating single view."""
        is_valid, msg = registry.validate_view_combination(["sales_fact"])
        assert is_valid
        assert msg == ""

    def test_validate_view_combination_multiple(self, registry):
        """Test validating multiple views."""
        # Valid combination
        is_valid, msg = registry.validate_view_combination(
            ["sales_fact", "customer_dim"]
        )
        assert is_valid

        # Invalid combination
        is_valid, msg = registry.validate_view_combination(
            ["sales_fact", "nonexistent"]
        )
        assert not is_valid
        assert "not found" in msg

    def test_validate_view_combination_empty(self, registry):
        """Test validating empty view list."""
        is_valid, msg = registry.validate_view_combination([])
        assert not is_valid
        assert "at least one" in msg

    def test_get_reachable_views(self, registry):
        """Test finding reachable views from a starting point."""
        reachable = registry.get_reachable_views("sales_fact")
        assert "sales_fact" in reachable  # Include self
        assert "customer_dim" in reachable
        assert "product_dim" in reachable

    def test_get_reachable_views_nonexistent(self, registry):
        """Test getting reachable views from nonexistent view."""
        reachable = registry.get_reachable_views("nonexistent")
        assert len(reachable) == 0

    def test_get_view_info(self, registry):
        """Test getting comprehensive view information."""
        info = registry.get_view_info("customer_dim")
        assert info is not None
        assert info["view"].name == "customer_dim"
        assert len(info["incoming_joins"]) > 0  # customer_dim has incoming joins
        assert len(info["outgoing_joins"]) == 0  # customer_dim has no outgoing joins

    def test_get_view_info_nonexistent(self, registry):
        """Test getting info for nonexistent view."""
        info = registry.get_view_info("nonexistent")
        assert info is None

    def test_registry_str_representation(self, registry):
        """Test string representation of registry."""
        str_repr = str(registry)
        assert "ViewRegistry" in str_repr
        assert "views=" in str_repr

    def test_duplicate_view_registration(self):
        """Test that duplicate view registration raises error."""
        reg = ViewRegistry()
        view = ViewSchema(
            name="test",
            view_type="fact",
            domain="test",
            columns=[ColumnSchema(name="id", data_type="INT")],
        )
        reg.register_view(view)

        with pytest.raises(ValueError):  # Duplicate view
            reg.register_view(view)

    def test_join_missing_view(self):
        """Test that join validation checks for missing views."""
        reg = ViewRegistry()
        view = ViewSchema(
            name="test",
            view_type="fact",
            domain="test",
            columns=[ColumnSchema(name="id", data_type="INT")],
        )
        reg.register_view(view)

        join = JoinRelationship(
            source_view="test",
            target_view="nonexistent",
            source_columns=["id"],
            target_columns=["id"],
            relationship_type="many_to_one",
        )

        with pytest.raises(ValueError):  # Target view missing
            reg.register_join(join)


class TestQueryRequest:
    """Test QueryRequest model."""

    def test_create_simple_query_request(self):
        """Test creating a simple query request."""
        req = QueryRequest(selected_views=["sales_fact"])
        assert req.selected_views == ["sales_fact"]
        assert req.limit == 100
        assert req.filters is None

    def test_create_complex_query_request(self):
        """Test creating a complex query request."""
        req = QueryRequest(
            selected_views=["sales_fact", "customer_dim"],
            filters={"region": "WEST"},
            limit=1000,
            aggregations={"amount": "SUM"},
            group_by=["region"],
        )
        assert len(req.selected_views) == 2
        assert req.filters == {"region": "WEST"}
        assert req.limit == 1000

    def test_query_request_validation_limit(self):
        """Test query request limit validation."""
        # High limits are now allowed at model level, validated at validator level
        req = QueryRequest(selected_views=["test"], limit=20000)
        assert req.limit == 20000

        # Low limits still validated at model level
        with pytest.raises(Exception):  # Limit too low
            QueryRequest(selected_views=["test"], limit=0)

    def test_query_request_requires_views(self):
        """Test that at least one view is required."""
        with pytest.raises(Exception):
            QueryRequest(selected_views=[])
