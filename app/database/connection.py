"""
Database Connection Management

Handles database connections with pooling, query execution, and metadata extraction.
Supports both real database connections (PostgreSQL/SQLite) and mock connections for testing.
"""

import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import sqlite3

logger = logging.getLogger(__name__)


class DbConnection:
    """
    Database connection manager with pooling and safe query execution.

    Provides a unified interface for database operations, supporting both
    real databases (via connection pooling) and mock databases (for testing).

    Attributes:
        connection_string: Database URL (e.g., sqlite:///:memory:)
        is_mock: Whether this is a mock connection (for testing)
    """

    def __init__(self, connection_string: str = "sqlite:///:memory:", is_mock: bool = False):
        """
        Initialize database connection.

        Args:
            connection_string: Database URL. Supports:
                - sqlite:///:memory: (in-memory SQLite)
                - sqlite:///path/to/db.sqlite (file-based SQLite)
                - postgresql://user:pass@host:5432/dbname (PostgreSQL)
            is_mock: If True, connection is mocked for testing
        """
        self.connection_string = connection_string
        self.is_mock = is_mock
        self._connection: Optional[Any] = None
        self._mock_data: Dict[str, List[Dict[str, Any]]] = {}

        if not is_mock:
            self.connect()

    def connect(self) -> None:
        """
        Establish database connection.

        For SQLite: Creates connection immediately
        For PostgreSQL: Would implement connection pooling (future)
        For mock: Initializes empty mock data store

        Raises:
            Exception: If connection fails
        """
        if self.is_mock:
            logger.debug("Mock database initialized")
            return

        try:
            if self.connection_string.startswith("sqlite://"):
                # Extract database path from connection string
                db_path = self.connection_string.replace("sqlite:///", "")
                if db_path == ":memory:":
                    db_path = ":memory:"

                self._connection = sqlite3.connect(db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
                logger.info(f"Connected to SQLite database: {db_path}")

            elif self.connection_string.startswith("postgresql://"):
                # PostgreSQL support (future implementation)
                raise NotImplementedError(
                    "PostgreSQL connections coming in Phase 2. Use SQLite for now."
                )
            else:
                raise ValueError(f"Unsupported database URL: {self.connection_string}")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a read query and return results.

        Args:
            sql: SQL query to execute (SELECT statements)
            params: Query parameters for parameterized queries (prevents SQL injection)

        Returns:
            List of result rows as dictionaries

        Raises:
            Exception: If query execution fails
        """
        if self.is_mock:
            logger.debug(f"Mock query execution: {sql}")
            # Return empty results for mock
            return []

        try:
            if not self._connection:
                raise RuntimeError("Database not connected. Call connect() first.")

            cursor = self._connection.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # Convert rows to dictionaries
            columns = [description[0] for description in cursor.description] if cursor.description else []
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            logger.debug(f"Query returned {len(rows)} rows")
            return rows

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"SQL: {sql}")
            raise

    def execute_script(self, sql: str) -> None:
        """
        Execute multiple SQL statements (for setup/teardown).

        Args:
            sql: SQL script with multiple statements

        Raises:
            Exception: If execution fails
        """
        if self.is_mock:
            logger.debug("Mock script execution")
            return

        try:
            if not self._connection:
                raise RuntimeError("Database not connected. Call connect() first.")

            self._connection.executescript(sql)
            self._connection.commit()
            logger.info("Script executed successfully")

        except Exception as e:
            logger.error(f"Script execution failed: {e}")
            raise

    def get_table_metadata(self, table_name: str) -> Dict[str, Any]:
        """
        Extract metadata about a table (columns, types, constraints).

        Args:
            table_name: Name of the table to inspect

        Returns:
            Dictionary with:
            - 'columns': List of column info dicts
            - 'row_count': Approximate row count
            - 'primary_keys': List of PK column names
            - 'foreign_keys': List of FK relationships

        Raises:
            Exception: If table doesn't exist or query fails
        """
        if self.is_mock:
            # Return mock metadata
            return {
                "columns": [],
                "row_count": 0,
                "primary_keys": [],
                "foreign_keys": [],
            }

        try:
            if not self._connection:
                raise RuntimeError("Database not connected.")

            cursor = self._connection.cursor()

            # Get table info (SQLite-specific, would need to adapt for PostgreSQL)
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns_raw = cursor.fetchall()

            if not columns_raw:
                raise ValueError(f"Table {table_name} not found")

            # Parse column metadata
            columns = []
            for col in columns_raw:
                columns.append(
                    {
                        "name": col[1],
                        "type": col[2],
                        "nullable": col[3] == 0,  # notnull flag
                        "primary_key": col[5] > 0,  # pk column number
                    }
                )

            # Get row count
            count_result = self.execute_query(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = count_result[0]["count"] if count_result else 0

            # Get foreign keys (SQLite-specific)
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            fk_raw = cursor.fetchall()

            foreign_keys = [
                {
                    "column": fk[3],
                    "references_table": fk[2],
                    "references_column": fk[4],
                }
                for fk in fk_raw
            ]

            return {
                "columns": columns,
                "row_count": row_count,
                "primary_keys": [col["name"] for col in columns if col["primary_key"]],
                "foreign_keys": foreign_keys,
            }

        except Exception as e:
            logger.error(f"Failed to get metadata for {table_name}: {e}")
            raise

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Usage:
            with db.transaction():
                db.execute_query(...)
                # Auto-commit on success, rollback on exception
        """
        if self.is_mock:
            yield
            return

        if not self._connection:
            raise RuntimeError("Database not connected.")

        try:
            yield
            self._connection.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            self._connection.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    def set_mock_data(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        """
        (Mock mode only) Set mock data for a table.

        Useful for testing when you don't want to set up a real database.

        Args:
            table_name: Name of table to populate
            data: List of row dictionaries
        """
        if not self.is_mock:
            raise RuntimeError("set_mock_data() only works in mock mode")

        self._mock_data[table_name] = data
        logger.debug(f"Mock data set for {table_name}: {len(data)} rows")

    def get_mock_data(self, table_name: str) -> List[Dict[str, Any]]:
        """
        (Mock mode only) Retrieve mock data for a table.

        Args:
            table_name: Name of table

        Returns:
            List of row dictionaries, or empty list if table doesn't exist
        """
        if not self.is_mock:
            raise RuntimeError("get_mock_data() only works in mock mode")

        return self._mock_data.get(table_name, [])

    def __repr__(self) -> str:
        """String representation of connection."""
        mode = "mock" if self.is_mock else "real"
        return f"DbConnection(mode={mode}, db={self.connection_string})"


# Global connection instance (lazy-loaded singleton)
_db_instance: Optional[DbConnection] = None


def get_db(
    connection_string: str = "sqlite:///:memory:",
    is_mock: bool = False,
    force_new: bool = False,
) -> DbConnection:
    """
    Get or create the global database connection.

    Args:
        connection_string: Database URL (ignored if instance already exists)
        is_mock: Use mock connection (ignored if instance already exists)
        force_new: If True, create a new connection even if one exists

    Returns:
        DbConnection instance
    """
    global _db_instance

    if force_new or _db_instance is None:
        _db_instance = DbConnection(connection_string, is_mock)

    return _db_instance


def reset_db() -> None:
    """Reset the global database connection (close and clear)."""
    global _db_instance

    if _db_instance:
        _db_instance.close()
        _db_instance = None

    logger.debug("Database connection reset")
