"""
Domain Onboarding Models

Pydantic models for registering new business domains at runtime
without modifying source code.
"""

from typing import List
from pydantic import BaseModel, Field


class DomainConfig(BaseModel):
    """
    Configuration for a dynamically-registered business domain.

    Attributes:
        name: URL-safe slug (e.g. "hr", "legal"). Must be unique.
        description: Human-readable description shown in domain listings.
        keywords: Terms used by the router to recognize queries for this domain.
        view_names: Names of database views this domain can access.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Lowercase slug identifying the domain (e.g. 'hr', 'legal')",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of the domain",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords the router uses to recognize queries for this domain",
    )
    view_names: List[str] = Field(
        default_factory=list,
        description="Names of database views accessible to this domain",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "hr",
                "description": "Human Resources domain — headcount, salaries, departments",
                "keywords": ["employee", "headcount", "salary", "department", "hire", "staff"],
                "view_names": ["employee_fact", "department_dim"],
            }
        }
