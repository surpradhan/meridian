# Phase 6 Completion: Advanced Query Capabilities

**Status**: ✅ COMPLETE  
**Date**: 2026-04-09  
**Tests Added**: 65 (in `tests/unit/test_phase6.py`)  
**Total Tests**: 441+ passing

---

## Overview

Phase 6 expanded MERIDIAN's query engine with SQL patterns, temporal intelligence, multi-hop join resolution, and result visualization hints — turning it from a basic SELECT/WHERE/GROUP BY system into one that can handle the full range of analytical queries business users ask.

---

## Deliverables

### 6.1 Complex SQL Support

**Files**: `app/query/builder.py`, `app/views/models.py`

#### New Pydantic models (`app/views/models.py`)

| Model | Purpose |
|-------|---------|
| `OrderByItem` | Typed `{column, direction: ASC\|DESC}` — replaces raw dicts |
| `WindowFunction` | `{alias, function, partition_by, order_by}` with `@validator` that whitelists function names |
| `CTEDefinition` | `{name, sql}` for WITH clause definitions |

`_VALID_WINDOW_FUNCTIONS` frozenset: `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, `SUM`, `AVG`, `COUNT`, `MIN`, `MAX`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`, `NTILE`, `CUME_DIST`, `PERCENT_RANK`

#### Extended `QueryRequest` fields

- `having: Optional[dict]` — HAVING conditions keyed by `"AGG_column"`, values `{op, value}`
- `order_by: Optional[List[OrderByItem]]`
- `window_functions: Optional[List[WindowFunction]]`
- `ctes: Optional[List[CTEDefinition]]`
- `time_expression: Optional[str]`
- `time_column: Optional[str]`

#### New QueryBuilder methods

- `build_query_parameterized(request)` → `(sql: str, params: List[Any])` — primary production path
- `build_query(request)` → `str` — backward-compatible, calls parameterized internally
- `_build_where_clause_parameterized(request, params, inline)` — `?` placeholders; `COLLATE NOCASE` on strings
- `_build_having_clause_parameterized(request, params, inline)` — whitelisted ops; numeric values only; `?` placeholders
- `_render_window_function(wf)` — `FUNC() OVER (PARTITION BY … ORDER BY …)`
- `_build_order_by_clause(request)` — uses `item.column`/`item.direction` typed attrs

#### Security: `_SAFE_HAVING_OPS`

```python
_SAFE_HAVING_OPS = frozenset({"=", "!=", "<>", ">", ">=", "<", "<="})
```

HAVING values that are not numeric raise `ValueError` before query execution.

---

### 6.2 Multi-Hop Join Pathfinding

**File**: `app/views/registry.py`

`ViewRegistry.find_join_path(from_view, to_view)` uses BFS with parent tracking to find the shortest join path through the registered join graph. Returns an ordered list of view names (inclusive of endpoints), or `None` if no path exists.

`QueryBuilder._build_from_clause()` calls `find_join_path` when two requested views have no direct join, automatically injecting bridge views so multi-hop queries work transparently.

`BaseDomainAgent.get_join_paths()` now delegates to `self.registry.find_join_path()` (previously a TODO stub).

---

### 6.3 Time Intelligence

**File**: `app/query/time_intelligence.py` (new)

Resolves natural-language temporal expressions into concrete ISO date ranges without requiring the user to specify exact dates.

**Supported expressions**:

| Expression | Resolves to |
|-----------|------------|
| `last_quarter` | First day of previous calendar quarter → last day of previous quarter |
| `this_quarter` | First day of current quarter → today |
| `last_month` | First → last day of previous month |
| `this_month` | First day of current month → today |
| `ytd` / `year_to_date` | Jan 1 of current year → today |
| `last_year` | Jan 1 → Dec 31 of previous year |
| `trailing_N_days` | today − N days → today |

`time_column` is validated against registered view columns before resolution — raises `ValueError` if the column is not found in any selected view.

Results are injected as parameterized WHERE conditions (`? COLLATE NOCASE` not applied — dates use direct `?` binding).

---

### 6.4 Parameterized Queries (SQL Injection Prevention)

**File**: `app/query/builder.py`

All user-supplied values (filter values, HAVING values, date range boundaries) are now bound as `?` parameters rather than interpolated into the SQL string. The production execution path (`BaseDomainAgent.execute_query_request`) exclusively uses `build_query_parameterized` and passes `params` to `db.execute_query`.

`build_query()` (the string API) is preserved for backward compatibility but internally calls the same parameterized builder — it formats the inline display SQL with escaped apostrophes (`''`) for logging/display purposes only.

---

### 6.5 Visualization Hints

**Files**: `app/visualization/__init__.py`, `app/visualization/chart_selector.py` (new), `app/agents/orchestrator.py`

`select_chart_type(rows)` examines result column types and row count to infer the most appropriate chart:

| Condition | Chart type |
|-----------|-----------|
| Has date/time column + one numeric | `line` |
| ≤ 8 rows, one string + one numeric | `pie` |
| ≥ 2 rows with string group + numeric | `bar` |
| Everything else | `table` |

Returns: `{chart_type, x_axis, y_axis, reason}`

`Orchestrator._build_visualization_hint()` wraps `select_chart_type` with a try/except so visualization failures never break query results. Every orchestrator result gains a `visualization` key.

---

## LLM Prompt Extension

`_build_interpret_prompt()` in `base_domain.py` was extended to describe the new QueryRequest fields to GPT-4:

- `having` — HAVING conditions with `op`/`value` structure
- `order_by` — list of `{column, direction}` objects
- `window_functions` — list of window function specs
- `time_expression` / `time_column` — temporal expression fields

`_try_llm_interpret()` parses window function specs from the LLM response and constructs `WindowFunction` objects (Pydantic validation applies immediately, catching invalid function names at construction time).

---

## Test Coverage

`tests/unit/test_phase6.py` — 65 tests across 12 test classes:

| Class | Coverage |
|-------|---------|
| `TestBFSJoinPathfinding` | Direct, multi-hop, disconnected paths |
| `TestQueryBuilderHaving` | HAVING generation and parameterization |
| `TestWindowFunctions` | ROW_NUMBER, RANK, SUM window specs |
| `TestCTEs` | WITH clause prepending |
| `TestOrderBy` | ORDER BY ASC/DESC |
| `TestTimeIntelligence` | All 7 expression types |
| `TestTimeIntelligenceDefaultDate` | `reference_date=None` uses `date.today()` |
| `TestVisualizationHints` | Line/bar/pie/table heuristics |
| `TestWindowFunctionValidation` | Invalid function name raises `ValueError` |
| `TestOrderByItemModel` | `OrderByItem` direction validation |
| `TestTimeColumnValidation` | Invalid `time_column` raises `ValueError` |
| `TestHavingValidation` | Unsafe operator and non-numeric value rejection |
| `TestParameterizedQuery` | `?` placeholder present; no literal values in SQL |

---

## Files Changed

| File | Change |
|------|--------|
| `app/views/models.py` | Added `OrderByItem`, `WindowFunction`, `CTEDefinition`; extended `QueryRequest` |
| `app/views/registry.py` | Added `find_join_path()` BFS method |
| `app/query/builder.py` | Added `build_query_parameterized`, HAVING, window, CTE, ORDER BY, time expression support |
| `app/query/time_intelligence.py` | **New file** — temporal expression resolver |
| `app/agents/domain/base_domain.py` | Extended LLM prompt; updated `execute_query_request` to use parameterized path; wired `get_join_paths()` |
| `app/agents/orchestrator.py` | Added `_build_visualization_hint()`; attached `visualization` to results |
| `app/visualization/__init__.py` | **New file** — package init |
| `app/visualization/chart_selector.py` | **New file** — chart type inference |
| `tests/unit/test_phase6.py` | **New file** — 65 tests |
| `tests/integration/test_agents.py` | Updated SQL assertions for parameterized output |
| `tests/integration/test_ui_queries.py` | Updated SQL assertions for parameterized output |
