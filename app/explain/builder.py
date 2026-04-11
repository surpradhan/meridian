"""
Explain Response Builder

Reshapes the raw orchestrator result + trace into a human-readable
explanation of *why* the system interpreted a query the way it did.

All data comes from the existing result dict — no additional LLM calls.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExplainResponse(BaseModel):
    """Structured explanation of a query interpretation."""

    query: str
    routing_decision: Dict[str, Any]
    views_selected: List[str]
    filters_extracted: Dict[str, Any]
    aggregations: Dict[str, Any]
    group_by: List[str]
    sql_generated: Optional[str]
    join_paths: List[str]
    time_resolution: Optional[Dict[str, Any]]
    interpretation_method: Optional[str]
    confidence: Optional[float]

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Total sales by region last quarter",
                "routing_decision": {
                    "domain": "sales",
                    "confidence": 0.95,
                    "reasoning": "Keywords: sales, region",
                },
                "views_selected": ["sales_fact", "region_dim"],
                "filters_extracted": {},
                "aggregations": {"amount": "SUM"},
                "group_by": ["region"],
                "sql_generated": "SELECT region, SUM(amount) FROM sales_fact ...",
                "join_paths": ["sales_fact -> region_dim"],
                "time_resolution": {
                    "expression": "last_quarter",
                    "start": "2025-10-01",
                    "end": "2025-12-31",
                },
                "interpretation_method": "llm",
                "confidence": 0.9,
            }
        }


def build_explain_response(
    query: str,
    result: Dict[str, Any],
    trace: Optional[Any] = None,
) -> ExplainResponse:
    """
    Build an ExplainResponse from the orchestrator result dict.

    Args:
        query: Original natural language query
        result: Dict returned by Orchestrator.process_query()
        trace: Optional execution trace (from process_query_with_trace)

    Returns:
        ExplainResponse with all available interpretation metadata
    """
    domain = result.get("domain", "unknown")
    routing_confidence = result.get("routing_confidence") or result.get("confidence") or 0.0

    # Routing decision
    routing_decision: Dict[str, Any] = {
        "domain": domain,
        "confidence": routing_confidence,
    }

    # Try to pull richer routing info from trace steps
    if isinstance(trace, list):
        for step in trace:
            if isinstance(step, dict) and step.get("step") == "routing":
                routing_decision["reasoning"] = step.get("reasoning") or step.get("result", "")
                break
    elif isinstance(trace, dict):
        routing_decision["reasoning"] = trace.get("routing_reasoning", "")

    # Views, filters, aggregations — extracted from result metadata
    views_selected: List[str] = result.get("views") or []

    # Try to get query details from trace
    filters: Dict[str, Any] = {}
    aggregations: Dict[str, Any] = {}
    group_by: List[str] = []
    join_paths: List[str] = []
    time_resolution: Optional[Dict[str, Any]] = None

    if isinstance(trace, list):
        for step in trace:
            if isinstance(step, dict) and step.get("step") in ("agent", "execution"):
                detail = step.get("detail") or step.get("result") or {}
                if isinstance(detail, dict):
                    filters = detail.get("filters") or filters
                    aggregations = detail.get("aggregations") or aggregations
                    group_by = detail.get("group_by") or group_by

    # Time resolution from result metadata
    time_expr = result.get("time_expression")
    if time_expr:
        time_resolution = {
            "expression": time_expr,
            "start": result.get("time_start"),
            "end": result.get("time_end"),
        }

    # Join paths: infer from views (A -> B format)
    if len(views_selected) > 1:
        join_paths = [
            f"{views_selected[i]} -> {views_selected[i + 1]}"
            for i in range(len(views_selected) - 1)
        ]

    return ExplainResponse(
        query=query,
        routing_decision=routing_decision,
        views_selected=views_selected,
        filters_extracted=filters,
        aggregations=aggregations,
        group_by=group_by,
        sql_generated=result.get("sql"),
        join_paths=join_paths,
        time_resolution=time_resolution,
        interpretation_method=result.get("interpretation_method"),
        confidence=result.get("confidence"),
    )
