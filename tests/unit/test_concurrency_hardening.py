"""
Regression tests for the concurrency hardening (review findings H4–H6).

- H4: SSE token drain must release the executor thread between polls and must
      still terminate if the end-of-stream sentinel is ever missed.
- H5: ConversationContext.messages/context must be safe under concurrent turns
      on the same conversation.
- H6: get_llm() must construct exactly one shared client under a concurrent
      first-call stampede.
"""

import threading
import time

import pytest

from app.agents import llm_client
from app.agents.streaming import MeridianStreamingCallback
from app.agents.conversation_context import ConversationContext


# ---------------------------------------------------------------------------
# H4 — streaming drain
# ---------------------------------------------------------------------------

class TestStreamingDrain:
    @pytest.mark.asyncio
    async def test_yields_tokens_then_stops_on_sentinel(self):
        cb = MeridianStreamingCallback()
        cb.on_llm_new_token("a")
        cb.on_llm_new_token("b")
        cb.mark_done()  # pushes the sentinel

        tokens = [t async for t in cb.aiter_tokens()]
        assert tokens == ["a", "b"]

    @pytest.mark.asyncio
    async def test_terminates_when_done_even_without_sentinel(self):
        # Simulate a missed sentinel: a token is queued and the producer is
        # marked done directly, without pushing _SENTINEL. The drained+done
        # fallback must still terminate the generator.
        cb = MeridianStreamingCallback()
        cb._queue.put("only")
        cb._done.set()

        tokens = [t async for t in cb.aiter_tokens()]
        assert tokens == ["only"]


# ---------------------------------------------------------------------------
# H5 — conversation context thread-safety
# ---------------------------------------------------------------------------

class TestConversationContextThreadSafety:
    def test_concurrent_add_message_loses_nothing(self):
        ctx = ConversationContext(max_history=10_000)
        n_threads, per_thread = 16, 50
        barrier = threading.Barrier(n_threads)
        errors = []

        def worker(tid):
            try:
                barrier.wait()
                for i in range(per_thread):
                    ctx.add_message("user", f"{tid}-{i}")
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(ctx.messages) == n_threads * per_thread

    def test_reads_during_concurrent_writes_do_not_raise(self):
        ctx = ConversationContext(max_history=100)
        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                ctx.add_message("user", f"m{i}")
                i += 1

        def reader():
            try:
                while not stop.is_set():
                    ctx.get_context_summary()
                    ctx.get_message_history(limit=5)
                    ctx.to_dict()
            except Exception as e:  # pragma: no cover - failure path
                errors.append(e)

        w = threading.Thread(target=writer)
        r = threading.Thread(target=reader)
        w.start()
        r.start()
        threading.Event().wait(0.3)
        stop.set()
        w.join()
        r.join()

        assert not errors


# ---------------------------------------------------------------------------
# H6 — single client under concurrent first-call
# ---------------------------------------------------------------------------

class TestGetLlmSingleInit:
    def test_concurrent_first_call_initializes_once(self, monkeypatch):
        llm_client.reset_llm_client()

        calls = {"n": 0}
        sentinel = object()

        def fake_init():
            # Sleep BEFORE incrementing to widen the check-then-act window the
            # way real (network) client construction does. Without the lock,
            # multiple threads would enter here concurrently and the count would
            # exceed 1 — so this test fails closed if the lock is removed.
            time.sleep(0.05)
            calls["n"] += 1
            llm_client._client = sentinel
            return sentinel

        monkeypatch.setattr(llm_client, "_initialize_client", fake_init)

        n_threads = 24
        barrier = threading.Barrier(n_threads)
        results = []

        def worker():
            barrier.wait()
            results.append(llm_client.get_llm())

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert calls["n"] == 1
        assert all(r is sentinel for r in results)

        llm_client.reset_llm_client()
