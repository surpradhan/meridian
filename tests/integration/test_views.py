"""
Integration Tests for View Registry with Database

Tests the interaction between the ViewRegistry and database layer,
ensuring they work together correctly to provide metadata access.
"""

import pytest
from app.views.registry import ViewRegistry, create_test_registry
from app.views.models import ViewSchema, ColumnSchema, JoinRelationship
from app.database.connection import DbConnection, get_db, reset_db


@pytest.fixture
def db_mock():
    """Create a mock database for testing."""
    reset_db()
    db = DbConnection(is_mock=True)
    yield db
    reset_db()


@pytest.fixture
def db_sqlite():
    """Create an in-memory SQLite database for testing."""
    reset_db()
    db = DbConnection(connection_string="sqlite:///:memory:", is_mock=False)
    yield db
    db.close()
    reset_db()


@pytest.fixture
def registry_with_db(db_sqlite):
    """Create registry with database connection."""
    registry = create_test_registry()
    return registry, db_sqlite


class TestRegistryWithDatabase:
    """Test registry operations with database backend."""

    def test_registry_loads_with_database(self, registry_with_db):
        """Test that registry initializes with database available."""
        registry, db = registry_with_db
        assert registry is not None
        assert len(registry.get_all_views()) > 0
        assert db is not None

    def test_database_connection_modes(self):
        """Test both mock and real database connection modes."""
        # Mock mode
        db_mock = DbConnection(is_mock=True)
        assert db_mock.is_mock is True
        db_mock.close()

        # Real mode (SQLite in-memory)
        db_real = DbConnection(connection_string="sqlite:///:memory:")
        assert db_real.is_mock is False
        db_real.close()

    def test_database_query_execution(self, db_sqlite):
        """Test executing queries against database."""
        # Create a test table
        db_sqlite.execute_script(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value REAL
            );

            INSERT INTO test_table (id, name, value) VALUES
                (1, 'Alice', 100.5),
                (2, 'Bob', 200.75),
                (3, 'Charlie', 150.25);
            """
        )

        # Query the table
        results = db_sqlite.execute_query("SELECT * FROM test_table ORDER BY id")

        assert len(results) == 3
        assert results[0]["name"] == "Alice"
        assert results[1]["value"] == 200.75

    def test_parameterized_queries_prevent_injection(self, db_sqlite):
        """Test that parameterized queries work and prevent SQL injection."""
        db_sqlite.execute_script(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                email TEXT
            );

            INSERT INTO users (username, email) VALUES ('alice', 'alice@example.com');
            INSERT INTO users (username, email) VALUES ('bob', 'bob@example.com');
            """
        )

        # Parameterized query (safe)
        results = db_sqlite.execute_query(
            "SELECT * FROM users WHERE username = ?", params=["alice"]
        )

        assert len(results) == 1
        assert results[0]["email"] == "alice@example.com"

    def test_registry_view_discovery_matches_domain_criteria(self, registry_with_db):
        """Test that views in registry meet business domain expectations."""
        registry, _ = registry_with_db

        # Check Sales domain
        sales_views = registry.get_views_by_domain("sales")
        assert len(sales_views) >= 3
        sales_names = [v.name for v in sales_views]
        assert "sales_fact" in sales_names
        assert "customer_dim" in sales_names

        # Check Finance domain
        finance_views = registry.get_views_by_domain("finance")
        assert len(finance_views) >= 2
        finance_names = [v.name for v in finance_views]
        assert "ledger_fact" in finance_names

        # Check Operations domain
        ops_views = registry.get_views_by_domain("operations")
        assert len(ops_views) >= 2

    def test_join_relationships_are_consistent(self, registry_with_db):
        """Test that join relationships are properly registered and bidirectional."""
        registry, _ = registry_with_db

        # Get all joins
        all_joins = registry.get_all_joins()
        assert len(all_joins) >= 7

        # Check specific join
        sales_to_customer = registry.find_joins("sales_fact", "customer_dim")
        assert sales_to_customer is not None
        assert sales_to_customer.relationship_type == "many_to_one"

        # Verify the join condition is valid
        condition = sales_to_customer.get_join_condition()
        assert "sales_fact.customer_id = customer_dim.customer_id" in condition

    def test_reachable_views_from_entry_point(self, registry_with_db):
        """Test that reachable views correctly identifies connected entities."""
        registry, _ = registry_with_db

        # From sales_fact, should be able to reach customer_dim and product_dim
        reachable = registry.get_reachable_views("sales_fact")

        assert "sales_fact" in reachable
        assert "customer_dim" in reachable
        assert "product_dim" in reachable

    def test_view_column_metadata_completeness(self, registry_with_db):
        """Test that view column metadata is complete and accurate."""
        registry, _ = registry_with_db

        sales_fact = registry.get_view("sales_fact")
        assert sales_fact is not None

        # Check column metadata
        columns = {col.name: col for col in sales_fact.columns}

        # Verify primary key
        assert "sale_id" in columns
        assert columns["sale_id"].is_primary_key is True
        assert columns["sale_id"].is_nullable is False

        # Verify foreign keys
        assert "customer_id" in columns
        assert columns["customer_id"].is_foreign_key is True

        # Verify regular columns
        assert "amount" in columns
        assert columns["amount"].data_type == "DECIMAL(12,2)"

    def test_registry_view_combinations_validity(self, registry_with_db):
        """Test view combination validation against registry."""
        registry, _ = registry_with_db

        # Valid single view
        is_valid, msg = registry.validate_view_combination(["sales_fact"])
        assert is_valid

        # Valid multiple views with joins
        is_valid, msg = registry.validate_view_combination(["sales_fact", "customer_dim"])
        assert is_valid

        # Invalid: nonexistent view
        is_valid, msg = registry.validate_view_combination(["sales_fact", "nonexistent_view"])
        assert not is_valid
        assert "not found" in msg

        # Invalid: empty list
        is_valid, msg = registry.validate_view_combination([])
        assert not is_valid
        assert "at least one" in msg

    def test_database_transaction_context_manager(self, db_sqlite):
        """Test database transaction handling."""
        db_sqlite.execute_script(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                balance REAL
            );
            INSERT INTO accounts VALUES (1, 1000.0);
            """
        )

        # Successful transaction
        with db_sqlite.transaction():
            db_sqlite.execute_query("UPDATE accounts SET balance = balance - 100 WHERE id = 1")

        result = db_sqlite.execute_query("SELECT balance FROM accounts WHERE id = 1")
        assert result[0]["balance"] == 900.0

    def test_registry_performance_under_load(self, registry_with_db):
        """Test registry performance with multiple operations."""
        registry, _ = registry_with_db
        import time

        start = time.time()

        # Perform multiple operations
        for _ in range(10):
            registry.get_all_views()
            registry.get_all_domains()
            registry.find_joins("sales_fact", "customer_dim")
            registry.get_reachable_views("ledger_fact")

        elapsed = (time.time() - start) * 1000
        assert elapsed < 1000  # All operations in < 1 second


class TestMockDatabaseMode:
    """Test mock database functionality for testing without real DB."""

    def test_mock_database_initialization(self, db_mock):
        """Test mock database can be created and used."""
        assert db_mock.is_mock is True

        # Mock data operations should work
        test_data = [
            {"id": 1, "name": "Test"},
            {"id": 2, "name": "Test2"},
        ]
        db_mock.set_mock_data("test_table", test_data)

        retrieved = db_mock.get_mock_data("test_table")
        assert len(retrieved) == 2

    def test_mock_query_returns_empty(self, db_mock):
        """Test that mock queries return empty results."""
        results = db_mock.execute_query("SELECT * FROM any_table")
        assert results == []

    def test_mock_transaction_context_manager(self, db_mock):
        """Test transaction context manager works with mock mode."""
        with db_mock.transaction():
            # Should not raise any errors
            pass

    def test_mock_metadata_retrieval(self, db_mock):
        """Test metadata retrieval in mock mode."""
        metadata = db_mock.get_table_metadata("any_table")

        assert metadata["columns"] == []
        assert metadata["row_count"] == 0
        assert metadata["primary_keys"] == []
        assert metadata["foreign_keys"] == []


class TestGlobalDatabaseInstance:
    """Test the global database instance management."""

    def test_get_db_singleton_behavior(self):
        """Test that get_db returns same instance."""
        reset_db()

        db1 = get_db(connection_string="sqlite:///:memory:")
        db2 = get_db(connection_string="sqlite:///:memory:")

        assert db1 is db2

        reset_db()

    def test_get_db_force_new_creates_separate_instance(self):
        """Test force_new parameter creates new instance."""
        reset_db()

        db1 = get_db(connection_string="sqlite:///:memory:")
        db2 = get_db(connection_string="sqlite:///:memory:", force_new=True)

        assert db1 is not db2

        db1.close()
        db2.close()
        reset_db()

    def test_reset_db_clears_singleton(self):
        """Test reset_db clears the global instance."""
        reset_db()

        db1 = get_db(connection_string="sqlite:///:memory:")
        reset_db()
        db2 = get_db(connection_string="sqlite:///:memory:")

        assert db1 is not db2

        db2.close()
        reset_db()
