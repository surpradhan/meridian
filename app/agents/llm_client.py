"""
Shared LLM Client

Module-level singleton for the ChatOpenAI client so all agents and the
router share one HTTP connection pool rather than creating a new client
per agent per request.

Also exposes `invoke_llm_with_retry` — a tenacity-backed wrapper that
retries on transient API errors (rate limits, timeouts, connection drops)
but NOT on non-transient errors (auth failures, bad requests, programming
errors), avoiding pointless retries that just add latency.
"""

import logging
import threading
from typing import Optional, Tuple, Type

logger = logging.getLogger(__name__)

# Thread-local LLM override — lets the streaming route inject a callback-equipped
# LLM for a single thread without affecting other concurrent requests.
_thread_local = threading.local()


def set_streaming_llm(client: object) -> None:
    """Override get_llm() for the current thread with a streaming-enabled client."""
    _thread_local.client = client


def clear_streaming_llm() -> None:
    """Remove the per-thread LLM override."""
    if hasattr(_thread_local, "client"):
        del _thread_local.client

# ---------------------------------------------------------------------------
# Tenacity retry helpers
# ---------------------------------------------------------------------------

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

    def retry(*args, **kwargs):  # type: ignore[misc]
        def decorator(func):
            return func
        return decorator

    def stop_after_attempt(n):  # type: ignore[misc]
        return None

    def wait_exponential(**kwargs):  # type: ignore[misc]
        return None

    def retry_if_exception_type(exc):  # type: ignore[misc]
        return None

# Transient OpenAI/LangChain errors worth retrying.
# Non-transient errors (AuthenticationError, InvalidRequestError, etc.) are
# intentionally excluded — retrying them wastes time and always fails.
try:
    import openai as _openai
    _TRANSIENT_LLM_ERRORS: Tuple[Type[Exception], ...] = (
        _openai.RateLimitError,
        _openai.APITimeoutError,
        _openai.APIConnectionError,
        _openai.InternalServerError,
        # Stdlib equivalents — always included so tests can use ConnectionError/TimeoutError
        # without instantiating the openai error subclasses (which require extra kwargs).
        ConnectionError,
        TimeoutError,
        OSError,
    )
except (ImportError, AttributeError):
    # openai not installed (e.g. test environments) — use stdlib equivalents only
    _TRANSIENT_LLM_ERRORS = (ConnectionError, TimeoutError, OSError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(_TRANSIENT_LLM_ERRORS),
    reraise=True,
)
def invoke_llm_with_retry(llm, prompt: str):
    """Invoke an LLM with exponential-backoff retry for transient API failures.

    Retries up to 3 times on rate limits, timeouts, and connection errors.
    Reraises immediately on auth failures, invalid requests, and all other
    non-transient exceptions so callers can fall back without wasted delay.
    """
    return llm.invoke(prompt)  # type: ignore[union-attr]

_client: Optional[object] = None
_init_attempted: bool = False


def get_llm() -> Optional[object]:
    """
    Return the shared LLM client, initializing it on first call.

    Provider priority: Groq (if GROQ_API_KEY is set) → OpenAI (if OPENAI_API_KEY is set).
    Returns None if neither key is configured.
    """
    # Per-thread override (used by streaming route to inject callbacks)
    thread_override = getattr(_thread_local, "client", None)
    if thread_override is not None:
        return thread_override

    global _client, _init_attempted
    if _init_attempted:
        return _client

    _init_attempted = True
    try:
        from app.config import settings

        if settings.groq_api_key:
            from langchain_groq import ChatGroq
            _client = ChatGroq(
                model=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=0,
                streaming=True,
            )
            logger.info(f"Shared LLM client initialized (provider: Groq, model: {settings.groq_model})")
        elif settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            _client = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
                streaming=True,
            )
            logger.info(f"Shared LLM client initialized (provider: OpenAI, model: {settings.openai_model})")
        else:
            logger.debug("No LLM API key configured (GROQ_API_KEY or OPENAI_API_KEY); LLM features disabled")
    except Exception as e:
        logger.warning(f"LLM client initialization failed: {e}")

    return _client


def reset_llm_client() -> None:
    """Reset the singleton — used in tests to inject a mock client."""
    global _client, _init_attempted
    _client = None
    _init_attempted = False
