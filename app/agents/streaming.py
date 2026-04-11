"""
Streaming Callback for Meridian

Provides a LangChain callback handler that captures LLM tokens into a queue
so they can be streamed to SSE clients as they arrive.
"""

import asyncio
import logging
import queue
import threading
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Union

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals end-of-stream


class MeridianStreamingCallback:
    """
    Thread-safe streaming callback for LangChain LLMs.

    Works with both sync and async callers:
    - Sync LLM threads push tokens via ``on_llm_new_token``
    - Async route handlers drain tokens via ``aiter_tokens()``

    Usage::

        callback = MeridianStreamingCallback()
        llm = get_llm().with_config({"callbacks": [callback]})
        # Run LLM in background thread, drain tokens in async generator
        async for token in callback.aiter_tokens():
            yield token
    """

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._done = threading.Event()

    # ------------------------------------------------------------------
    # LangChain callback interface (called from LLM thread)
    # ------------------------------------------------------------------

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Called by LangChain for each new streamed token."""
        self._queue.put(token)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Called when the LLM finishes generating."""
        self._queue.put(_SENTINEL)
        self._done.set()

    def on_llm_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any) -> None:
        """Called if the LLM raises an error."""
        logger.error(f"Streaming LLM error: {error}")
        self._queue.put(_SENTINEL)
        self._done.set()

    # ------------------------------------------------------------------
    # Consumer interface
    # ------------------------------------------------------------------

    def iter_tokens(self) -> Generator[str, None, None]:
        """Synchronous generator — yields tokens as they arrive."""
        while True:
            token = self._queue.get()
            if token is _SENTINEL:
                break
            yield token

    async def aiter_tokens(self) -> AsyncGenerator[str, None]:
        """Async generator — yields tokens without blocking the event loop."""
        loop = asyncio.get_running_loop()
        while True:
            # Poll the sync queue in the thread pool to avoid blocking
            token = await loop.run_in_executor(None, self._queue.get)
            if token is _SENTINEL:
                break
            yield token

    def mark_done(self) -> None:
        """Manually signal end-of-stream (e.g. non-streaming fallback path)."""
        self._queue.put(_SENTINEL)
        self._done.set()
