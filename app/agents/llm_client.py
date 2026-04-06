"""
Shared LLM Client

Module-level singleton for the ChatOpenAI client so all agents and the
router share one HTTP connection pool rather than creating a new client
per agent per request.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client: Optional[object] = None
_init_attempted: bool = False


def get_llm() -> Optional[object]:
    """
    Return the shared ChatOpenAI client, initializing it on first call.

    Returns None (and logs a warning) if the OpenAI API key is not set
    or if the langchain_openai package is unavailable.
    """
    global _client, _init_attempted
    if _init_attempted:
        return _client

    _init_attempted = True
    try:
        from app.config import settings
        if not settings.openai_api_key:
            logger.debug("No OpenAI API key configured; LLM features disabled")
            return None
        from langchain_openai import ChatOpenAI
        _client = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        logger.info(f"Shared LLM client initialized (model: {settings.openai_model})")
    except Exception as e:
        logger.warning(f"LLM client initialization failed: {e}")

    return _client


def reset_llm_client() -> None:
    """Reset the singleton — used in tests to inject a mock client."""
    global _client, _init_attempted
    _client = None
    _init_attempted = False
