"""
Streaming Callback for Meridian

Provides a LangChain callback handler that captures LLM tokens into a queue
so they can be streamed to SSE clients as they arrive.
"""

import asyncio
import logging
import queue
import threading
from typing import Any, AsyncGenerator, Generator, Union

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals end-of-stream

# How long a single blocking queue.get() may occupy an executor thread before
# it is released back to the pool. Bounding this prevents concurrent SSE streams
# from each pinning a default-executor thread for the full duration of an LLM
# call, which would otherwise starve every other run_in_executor user.
_POLL_TIMEOUT_SECONDS = 0.5


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
        """Async generator — yields tokens without blocking the event loop.

        Each poll occupies an executor thread for at most ``_POLL_TIMEOUT_SECONDS``
        (rather than the full duration of the LLM call), so many concurrent
        streams don't exhaust the shared default executor. Termination is driven
        by the end-of-stream sentinel, with a drained+done fallback so the
        generator can't hang if the sentinel is ever missed.
        """
        loop = asyncio.get_running_loop()
        while True:
            try:
                token = await loop.run_in_executor(
                    None, self._queue.get, True, _POLL_TIMEOUT_SECONDS
                )
            except queue.Empty:
                # No token within the poll window. Stop if the producer is done
                # and nothing remains; otherwise release the thread and re-poll.
                if self._done.is_set() and self._queue.empty():
                    break
                continue
            if token is _SENTINEL:
                break
            yield token

    def mark_done(self) -> None:
        """Manually signal end-of-stream (e.g. non-streaming fallback path)."""
        self._queue.put(_SENTINEL)
        self._done.set()
