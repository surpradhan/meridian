"""
Streaming Query API Route

SSE endpoint that streams LLM tokens as they are generated, then sends
a final JSON result event when the query completes.
"""

import asyncio
import json
import logging
import threading
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.store import User
from app.agents.streaming import MeridianStreamingCallback

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


class StreamQueryRequest(BaseModel):
    """Request body for streaming queries."""

    question: str = Field(..., min_length=1)
    domain: Optional[str] = None
    conversation_id: Optional[str] = None

    class Config:
        json_schema_extra = {"example": {"question": "Show total sales by region"}}


def _sse_event(data: Dict[str, Any]) -> str:
    """Format a dict as a Server-Sent Events data line."""
    return f"data: {json.dumps(data)}\n\n"


async def _stream_query(
    question: str,
    domain: Optional[str],
    conversation_id: Optional[str],
    callback: MeridianStreamingCallback,
) -> AsyncGenerator[str, None]:
    """
    Async generator that:
    1. Yields token events as LLM produces them
    2. Yields a final result event with the full orchestrator response
    """
    from app.views.registry import get_registry
    from app.database.connection import get_db
    from app.agents.orchestrator import Orchestrator
    from app.agents.llm_client import get_llm
    from app.config import settings

    registry = get_registry()
    db = get_db(connection_string=settings.database_url)
    orchestrator = Orchestrator(registry, db)

    # Inject the streaming callback into the LLM for this request only.
    # The orchestrator runs synchronously in a thread so the event loop stays free.
    result_holder: Dict[str, Any] = {}
    error_holder: Dict[str, str] = {}

    def _run_query() -> None:
        try:
            # Temporarily patch LLM with streaming callback
            llm = get_llm()
            if llm is not None:
                try:
                    streaming_llm = llm.with_config({"callbacks": [callback]})
                    # Patch the orchestrator's router and agents to use the streaming LLM
                    orchestrator.router._llm_override = streaming_llm
                except Exception:
                    pass  # If patching fails, fall back to non-streaming

            result = orchestrator.process_query(
                question,
                conversation_id=conversation_id,
                forced_domain=domain,
            )
            result_holder["data"] = result
        except Exception as e:
            error_holder["error"] = str(e)
        finally:
            callback.mark_done()

    # Run orchestrator in thread pool to keep async loop unblocked
    loop = asyncio.get_event_loop()
    thread = threading.Thread(target=_run_query, daemon=True)
    thread.start()

    # Stream tokens as they arrive
    async for token in callback.aiter_tokens():
        yield _sse_event({"type": "token", "content": token})

    # Wait for thread to finish
    await loop.run_in_executor(None, thread.join)

    # Send final result or error
    if error_holder:
        yield _sse_event({"type": "error", "message": error_holder["error"]})
    elif result_holder:
        yield _sse_event({"type": "result", "data": result_holder["data"]})

    # SSE close event
    yield _sse_event({"type": "done"})


@router.post("/api/query/stream")
async def stream_query(
    request: StreamQueryRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream a query response using Server-Sent Events.

    Events emitted:
    - ``{"type": "token", "content": "<text>"}`` — LLM token as generated
    - ``{"type": "result", "data": {...}}`` — full query result on completion
    - ``{"type": "error", "message": "..."}`` — if query fails
    - ``{"type": "done"}`` — stream closed

    Clients should use ``EventSource`` or ``fetch`` with ``ReadableStream``.
    """
    if not current_user.can_execute_queries():
        raise HTTPException(status_code=403, detail="Your role does not permit query execution.")

    callback = MeridianStreamingCallback()

    return StreamingResponse(
        _stream_query(
            question=request.question,
            domain=request.domain,
            conversation_id=request.conversation_id,
            callback=callback,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
