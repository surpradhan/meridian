"""
Query API Routes

REST endpoints for submitting and processing natural language queries.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.permissions import mask_sensitive_fields
from app.auth.store import User
from app.query.pagination import Paginator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query"])


class QueryRequest(BaseModel):
    """Request model for natural language query."""

    question: str = Field(..., description="Natural language question", min_length=1)
    auto_route: Optional[bool] = Field(
        default=True, description="Automatically route to appropriate domain"
    )
    domain: Optional[str] = Field(
        default=None, description="Specific domain (sales, finance, operations) - optional if auto_route=True"
    )
    trace: Optional[bool] = Field(
        default=False, description="Include execution trace in response"
    )
    page: Optional[int] = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: Optional[int] = Field(default=100, ge=1, le=10000, description="Rows per page")
    conversation_id: Optional[str] = Field(
        default=None,
        description="Session ID for multi-turn conversation context. "
                    "Omit to start a new conversation; reuse to continue an existing one.",
    )

    class Config:
        """Example for documentation."""

        json_schema_extra = {
            "example": {
                "question": "How many sales were made in the WEST region?",
                "auto_route": True,
                "trace": False,
            }
        }


class QueryResponse(BaseModel):
    """Response model for query results."""

    result: Optional[Any] = Field(default=None, description="Result rows (list or dict)")
    row_count: Optional[int] = Field(default=None, description="Number of rows returned")
    sql: Optional[str] = Field(default=None, description="SQL query executed")
    views: Optional[list] = Field(default=None, description="Views accessed")
    domain: str = Field(description="Domain that handled the query")
    routing_confidence: Optional[float] = Field(default=None, description="Confidence of domain routing")
    confidence: Optional[float] = Field(default=None, description="Overall confidence score 0-1")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    state: str = Field(description="Execution state (complete, error)")
    trace: Optional[Any] = Field(default=None, description="Execution trace if requested")
    pagination: Optional[Dict[str, Any]] = Field(default=None, description="Pagination metadata")
    needs_clarification: Optional[bool] = Field(
        default=None,
        description="True when routing confidence is too low and user input is needed",
    )
    clarification_message: Optional[str] = Field(
        default=None,
        description="Human-readable message explaining what clarification is needed",
    )
    suggested_domains: Optional[list] = Field(
        default=None,
        description="Domain names the user might clarify their question toward",
    )
    interpretation_method: Optional[str] = Field(
        default=None,
        description="How the query was interpreted: 'llm' or 'regex'",
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Session ID — pass back in subsequent requests for multi-turn context",
    )
    suggestions: Optional[list] = Field(
        default=None,
        description="Suggested follow-up questions based on the current query and result",
    )

    class Config:
        """Allow extra fields from orchestrator and provide schema example."""
        extra = "allow"
        json_schema_extra = {
            "example": {
                "result": [
                    {"customer_id": 1, "total_sales": 5000.0},
                    {"customer_id": 2, "total_sales": 3500.0},
                ],
                "row_count": 2,
                "sql": "SELECT customer_id, SUM(amount) FROM sales_fact GROUP BY customer_id",
                "views": ["sales_fact"],
                "domain": "sales",
                "routing_confidence": 0.95,
                "confidence": 0.85,
                "state": "complete",
            }
        }


@router.post("/execute", response_model=QueryResponse)
async def execute_query(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Execute a natural language query using multi-agent orchestration.

    Takes a natural language question and automatically routes to the appropriate
    domain agent (sales, finance, operations) based on query content.

    Args:
        request: QueryRequest with question, routing options, trace flag

    Returns:
        QueryResponse with results, domain info, and execution metadata

    Raises:
        HTTPException: If query execution fails
    """
    logger.info(f"Query received from {current_user.username}: {request.question}")

    if not current_user.can_execute_queries():
        raise HTTPException(
            status_code=403,
            detail="Your role does not permit query execution. Contact an admin.",
        )

    try:
        # Import here to avoid circular imports
        from app.views.registry import get_registry
        from app.database.connection import get_db
        from app.agents.orchestrator import Orchestrator
        from app.config import settings

        # Get instances
        registry = get_registry()
        db = get_db(connection_string=settings.database_url)

        # Create orchestrator
        orchestrator = Orchestrator(registry, db)

        # Process query
        if request.trace:
            result = orchestrator.process_query_with_trace(
                request.question, conversation_id=request.conversation_id
            )
            # Convert trace result to standard response format
            if "error" in result:
                error_result = {
                    "domain": result.get("domain", "unknown"),
                    "confidence": 0.0,
                    "error": result["error"],
                    "state": result.get("state", "error"),
                    "trace": result if request.trace else None,
                }
                return error_result

            result["trace"] = result.get("steps", [])
        else:
            result = orchestrator.process_query(
                request.question, conversation_id=request.conversation_id
            )

        # Domain access check — verify user is allowed into the routed domain
        routed_domain = result.get("domain", "")
        if routed_domain and not current_user.can_access_domain(routed_domain):
            raise HTTPException(
                status_code=403,
                detail=f"Access to domain '{routed_domain}' is not permitted for your account",
            )

        # Check for errors
        if "error" in result:
            error_response = {
                "domain": result.get("domain", "unknown"),
                "routing_confidence": result.get("routing_confidence", 0.0),
                "confidence": result.get("confidence", 0.0),
                "error": result["error"],
                "state": result.get("state", "error"),
            }
            if request.trace:
                error_response["trace"] = result.get("trace")
            return error_response

        logger.info(
            f"Query executed successfully. Domain: {result.get('domain')}, "
            f"Rows: {result.get('row_count', 0)}, Confidence: {result.get('confidence', 0)}"
        )

        # Apply pagination to result rows.
        # row_count preserves the total from the DB; page_row_count is rows on this page.
        rows = result.get("result") or []
        if isinstance(rows, list):
            paginator = Paginator()
            paginated = paginator.paginate(rows, page=request.page or 1, page_size=request.page_size or 100)
            result["result"] = paginated.rows
            result["page_row_count"] = len(paginated.rows)
            result["pagination"] = paginated.to_dict()["pagination"]

        # Mask sensitive fields based on user role
        if "result" in result:
            result["result"] = mask_sensitive_fields(result["result"], current_user.role)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@router.post("/validate")
async def validate_query(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Validate a query without executing it.

    Checks if a query is valid for the specified or routed domain.

    Args:
        request: QueryRequest with question and optional domain

    Returns:
        Dict with validation results
    """
    logger.info(f"Validating query: {request.question}")

    try:
        from app.views.registry import get_registry
        from app.database.connection import get_db
        from app.agents.orchestrator import Orchestrator

        registry = get_registry()
        db = get_db()
        orchestrator = Orchestrator(registry, db)

        # Determine domain
        if request.auto_route or not request.domain:
            domain, confidence = orchestrator.router.route(request.question)
        else:
            domain = request.domain
            confidence = 1.0

        # Validate
        is_valid, errors = orchestrator.validate_query_for_domain(domain, request.question)

        return {
            "is_valid": is_valid,
            "domain": domain,
            "confidence": confidence,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/domains")
async def list_domains(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """
    List all available domains and their capabilities.

    Returns information about all supported domains (sales, finance, operations).

    Returns:
        Dict with domains and their capabilities
    """
    logger.info("Listing available domains")

    try:
        from app.views.registry import get_registry
        from app.database.connection import get_db
        from app.agents.orchestrator import Orchestrator

        registry = get_registry()
        db = get_db()
        orchestrator = Orchestrator(registry, db)

        domains = orchestrator.get_all_domains()

        return {
            "domains": domains,
            "count": len(domains),
        }

    except Exception as e:
        logger.error(f"Domain listing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Domain listing failed: {str(e)}")


@router.get("/explore")
async def explore_domain(
    domain: str = Query("sales", description="Domain to explore"),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Explore available views and metadata in a domain.

    Returns information about views, columns, and relationships in the domain.

    Args:
        domain: Domain name (sales, finance, operations)

    Returns:
        Dict with domain metadata and suggestions
    """
    logger.info(f"Exploring domain: {domain}")

    if not current_user.can_access_domain(domain):
        raise HTTPException(
            status_code=403,
            detail=f"Access to domain '{domain}' is not permitted for your account",
        )

    try:
        from app.views.registry import get_registry
        from app.database.connection import get_db
        from app.agents.orchestrator import Orchestrator

        registry = get_registry()
        db = get_db()
        orchestrator = Orchestrator(registry, db)

        capabilities = orchestrator.get_domain_capabilities(domain)

        if "error" in capabilities:
            raise HTTPException(status_code=400, detail=capabilities["error"])

        return capabilities

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Exploration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Exploration failed: {str(e)}")


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns status of query service components.
    """
    try:
        from app.views.registry import get_registry
        from app.database.connection import get_db

        registry = get_registry()
        db = get_db()

        return {
            "status": "healthy",
            "components": {
                "registry": "ok" if registry else "failed",
                "database": "ok" if db else "failed",
            },
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }
