"""
Unit tests for SQL syntax validation in QueryValidator.
"""

import pytest
from unittest.mock import MagicMock
from app.query.validator import QueryValidator, reset_validator


@pytest.fixture(autouse=True)
def reset():
    reset_validator()
    yield
    reset_validator()


@pytest.fixture
def validator():
    registry = MagicMock()
    registry.validate_view_combination.return_value = (True, "")
    return QueryValidator(registry)


class TestValidateSqlSyntax:
    def test_valid_simple_select(self, validator):
        sql = "SELECT id, name FROM users LIMIT 100"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is True
        assert errors == []

    def test_valid_parameterized_select(self, validator):
        sql = "SELECT id FROM sales WHERE region = ? LIMIT 50"
        valid, errors = validator.validate_sql_syntax(sql, params=["WEST"])
        assert valid is True
        assert errors == []

    def test_valid_with_aggregation(self, validator):
        sql = "SELECT region, SUM(amount) AS total FROM sales_fact GROUP BY region LIMIT 100"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is True
        assert errors == []

    def test_valid_with_cte(self, validator):
        sql = (
            "WITH ranked AS (SELECT id, ROW_NUMBER() OVER (ORDER BY amount DESC) AS rn FROM t) "
            "SELECT * FROM ranked WHERE rn <= 10"
        )
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is True
        assert errors == []

    def test_missing_table_is_not_an_error(self, validator):
        # Views exist in the real DB, not the in-memory validator — must pass
        sql = "SELECT * FROM vw_sales_by_region LIMIT 100"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is True
        assert errors == []

    def test_missing_column_is_not_an_error(self, validator):
        sql = "SELECT nonexistent_col FROM some_view LIMIT 10"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is True
        assert errors == []

    def test_syntax_error_missing_from(self, validator):
        # FROM followed immediately by WHERE is a parse error (WHERE is not a table name)
        sql = "SELECT id FROM WHERE region = 'WEST'"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is False
        assert len(errors) == 1
        assert "syntax error" in errors[0].lower()

    def test_syntax_error_unclosed_paren(self, validator):
        sql = "SELECT id FROM sales WHERE (region = 'WEST' LIMIT 10"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is False
        assert len(errors) == 1

    def test_syntax_error_invalid_keyword(self, validator):
        sql = "SELEKT id FROM sales"
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is False

    def test_empty_params_list(self, validator):
        sql = "SELECT 1"
        valid, errors = validator.validate_sql_syntax(sql, params=[])
        assert valid is True
        assert errors == []

    def test_none_params(self, validator):
        sql = "SELECT 1"
        valid, errors = validator.validate_sql_syntax(sql, params=None)
        assert valid is True
        assert errors == []

    def test_multiple_params(self, validator):
        # Param count is derived from ? placeholders in SQL, not from caller's list.
        sql = "SELECT * FROM t WHERE a = ? AND b = ? AND c = ? LIMIT ?"
        valid, errors = validator.validate_sql_syntax(sql, params=["x", 1, True, 10])
        # Missing table — not a syntax error; 4 placeholders → 4 dummy params
        assert valid is True

    def test_mismatched_caller_params_dont_break_validation(self, validator):
        # Caller passes 2 params but SQL has 4 placeholders.
        # Validator should count from SQL, not from caller list, so no binding error.
        sql = "SELECT * FROM t WHERE a = ? AND b = ? AND c = ? LIMIT ?"
        valid, errors = validator.validate_sql_syntax(sql, params=["x", 1])
        assert valid is True  # missing table, not a syntax error

    def test_valid_having_clause(self, validator):
        sql = (
            "SELECT region, COUNT(*) AS cnt FROM t "
            "GROUP BY region HAVING COUNT(*) > ? LIMIT 100"
        )
        valid, errors = validator.validate_sql_syntax(sql, params=[5])
        assert valid is True

    def test_valid_window_function(self, validator):
        sql = (
            "SELECT id, RANK() OVER (PARTITION BY region ORDER BY amount DESC) AS rnk "
            "FROM t LIMIT 100"
        )
        valid, errors = validator.validate_sql_syntax(sql)
        assert valid is True
