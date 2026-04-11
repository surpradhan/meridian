"""Query explain mode — surfaces routing decisions and SQL generation rationale."""

from app.explain.builder import ExplainResponse, build_explain_response

__all__ = ["ExplainResponse", "build_explain_response"]
