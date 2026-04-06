"""
Unit tests for Phase 3 LLM features.

Covers LLM routing, query interpretation, clarification responses, and
fallback behaviour by injecting mock LLM clients via patch.

Patch targets:
  - app.agents.router.get_llm        (RouterAgent calls get_llm())
  - app.agents.domain.base_domain.get_llm  (BaseDomainAgent calls get_llm())
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.views.registry import create_test_registry
from app.database.connection import DbConnection, reset_db
from app.query.builder import QueryBuilder
from app.agents.llm_client import reset_llm_client
from app.agents.domain.sales import SalesAgent
from app.agents.orchestrator import Orchestrator, CLARIFICATION_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def llm_response(content: str) -> MagicMock:
    """Build a mock LLM response object with the given string content."""
    resp = MagicMock()
    resp.content = content
    return resp


def mock_llm(content: str) -> MagicMock:
    """Return a mock LLM client whose .invoke() returns the given content."""
    client = MagicMock()
    client.invoke.return_value = llm_response(content)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_llm_singleton():
    """Reset the shared LLM singleton before and after every test."""
    reset_llm_client()
    yield
    reset_llm_client()


@pytest.fixture
def registry():
    reset_db()
    return create_test_registry()


@pytest.fixture
def orchestrator(registry):
    return Orchestrator(registry, DbConnection(is_mock=True))


@pytest.fixture
def sales_agent(registry):
    return SalesAgent(registry, DbConnection(is_mock=True), QueryBuilder(registry))


# ---------------------------------------------------------------------------
# LLM routing
# ---------------------------------------------------------------------------

class TestLLMRouting:
    """RouterAgent uses LLM when available and falls back correctly."""

    def test_llm_result_used_when_client_available(self, orchestrator):
        """LLM classification overrides keyword scoring."""
        llm = mock_llm('{"domain": "finance", "confidence": 0.95, "reasoning": "about accounts"}')
        with patch("app.agents.router.get_llm", return_value=llm):
            domain, confidence = orchestrator.router.route("some ambiguous query")
        assert domain == "finance"
        assert confidence == pytest.approx(0.95)

    def test_fallback_to_keywords_on_llm_error(self, orchestrator):
        """Falls back to keyword routing when LLM raises an exception."""
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("OpenAI unavailable")
        with patch("app.agents.router.get_llm", return_value=llm):
            domain, confidence = orchestrator.router.route("total sales by region")
        assert domain == "sales"
        assert confidence > 0

    def test_fallback_to_keywords_on_unparseable_json(self, orchestrator):
        """Falls back when LLM returns text that contains no JSON object."""
        llm = mock_llm("Sorry, I cannot classify this.")
        with patch("app.agents.router.get_llm", return_value=llm):
            domain, _ = orchestrator.router.route("total inventory levels")
        assert domain == "operations"  # keyword: "inventory"

    def test_fallback_to_keywords_on_unknown_domain(self, orchestrator):
        """Falls back when LLM returns a domain name outside the allowed set."""
        llm = mock_llm('{"domain": "marketing", "confidence": 0.9, "reasoning": "..."}')
        with patch("app.agents.router.get_llm", return_value=llm):
            domain, _ = orchestrator.router.route("account balance")
        assert domain == "finance"  # keyword: "account"

    def test_confidence_clamped_above_one(self, orchestrator):
        """LLM confidence > 1.0 is clamped to 1.0."""
        llm = mock_llm('{"domain": "sales", "confidence": 1.8, "reasoning": "..."}')
        with patch("app.agents.router.get_llm", return_value=llm):
            _, confidence = orchestrator.router.route("sales revenue")
        assert confidence == pytest.approx(1.0)

    def test_confidence_clamped_below_zero(self, orchestrator):
        """LLM confidence < 0.0 is clamped to 0.0."""
        llm = mock_llm('{"domain": "sales", "confidence": -0.5, "reasoning": "..."}')
        with patch("app.agents.router.get_llm", return_value=llm):
            _, confidence = orchestrator.router.route("sales revenue")
        assert confidence == pytest.approx(0.0)

    def test_keyword_routing_used_when_no_llm(self, orchestrator):
        """Keyword routing is used when get_llm() returns None."""
        with patch("app.agents.router.get_llm", return_value=None):
            domain, _ = orchestrator.router.route("total warehouse shipments")
        assert domain == "operations"


# ---------------------------------------------------------------------------
# LLM query interpretation
# ---------------------------------------------------------------------------

class TestLLMQueryInterpretation:
    """Domain agents use LLM interpretation when available and fall back correctly."""

    def test_llm_interpretation_used_when_available(self, sales_agent):
        """Agent processes an LLM-generated QueryRequest and marks method as 'llm'."""
        payload = json.dumps({
            "selected_views": ["sales_fact", "customer_dim"],
            "filters": {"region": "WEST"},
            "aggregations": {"amount": "SUM"},
            "group_by": ["name"],
        })
        llm = mock_llm(payload)
        with patch("app.agents.domain.base_domain.get_llm", return_value=llm):
            result = sales_agent.process_query("Total sales by customer in the WEST region")
        assert result.get("interpretation_method") == "llm"
        assert "error" not in result

    def test_fallback_to_regex_on_unparseable_json(self, sales_agent):
        """Agent falls back to regex when LLM response contains no JSON."""
        llm = mock_llm("I cannot parse this query.")
        with patch("app.agents.domain.base_domain.get_llm", return_value=llm):
            result = sales_agent.process_query("How many sales were made?")
        assert result.get("interpretation_method") == "regex"
        assert "error" not in result

    def test_fallback_to_regex_on_empty_views(self, sales_agent):
        """Agent falls back to regex when LLM returns an empty selected_views list."""
        llm = mock_llm('{"selected_views": [], "filters": {}, "aggregations": {}, "group_by": []}')
        with patch("app.agents.domain.base_domain.get_llm", return_value=llm):
            result = sales_agent.process_query("How many sales were made?")
        assert result.get("interpretation_method") == "regex"
        assert "error" not in result

    def test_fallback_to_regex_when_llm_execute_fails(self, sales_agent):
        """Agent falls back to regex when the LLM-generated QueryRequest fails to execute.

        Simulates the LLM hallucinating a view that doesn't exist in the registry,
        causing validate_view_combination to reject it.
        """
        payload = json.dumps({
            "selected_views": ["hallucinated_view"],
            "filters": {},
            "aggregations": {},
            "group_by": [],
        })
        llm = mock_llm(payload)
        with patch("app.agents.domain.base_domain.get_llm", return_value=llm):
            result = sales_agent.process_query("How many sales were made?")
        # Must NOT return an error — the regex fallback should have succeeded
        assert result.get("interpretation_method") == "regex"
        assert "error" not in result

    def test_regex_used_when_no_llm(self, sales_agent):
        """Agent uses regex interpretation when get_llm() returns None."""
        with patch("app.agents.domain.base_domain.get_llm", return_value=None):
            result = sales_agent.process_query("How many sales were made?")
        assert result.get("interpretation_method") == "regex"
        assert "error" not in result


# ---------------------------------------------------------------------------
# Clarification
# ---------------------------------------------------------------------------

class TestClarification:
    """Orchestrator requests clarification when routing confidence is too low."""

    def test_low_llm_confidence_returns_clarification(self, orchestrator):
        """process_query returns a clarification response when LLM confidence is below threshold."""
        low = CLARIFICATION_THRESHOLD - 0.05
        llm = mock_llm(f'{{"domain": "sales", "confidence": {low}, "reasoning": "unclear"}}')
        with patch("app.agents.router.get_llm", return_value=llm):
            result = orchestrator.process_query("xyzzy plugh frobozz")
        assert result.get("needs_clarification") is True
        assert result.get("clarification_message")
        assert result.get("suggested_domains") == ["sales", "finance", "operations"]
        assert result["state"] == "complete"

    def test_sufficient_confidence_proceeds_normally(self, orchestrator):
        """process_query proceeds when LLM confidence is at or above threshold."""
        high = CLARIFICATION_THRESHOLD + 0.1
        llm = mock_llm(f'{{"domain": "sales", "confidence": {high}, "reasoning": "clear"}}')
        with patch("app.agents.router.get_llm", return_value=llm):
            # Also patch the agent-side LLM to avoid an actual OpenAI call
            with patch("app.agents.domain.base_domain.get_llm", return_value=None):
                result = orchestrator.process_query("total sales by region")
        assert result.get("needs_clarification") is not True
        assert result.get("domain") == "sales"

    def test_clarification_response_is_not_cached(self, orchestrator):
        """A clarification response must never be written to the cache."""
        low = CLARIFICATION_THRESHOLD - 0.05
        llm = mock_llm(f'{{"domain": "sales", "confidence": {low}, "reasoning": "unclear"}}')
        query = "xyzzy plugh frobozz"
        with patch("app.agents.router.get_llm", return_value=llm):
            orchestrator.process_query(query)
        assert orchestrator.cache.get_result(query) is None

    def test_trace_path_returns_clarification_on_low_confidence(self, orchestrator):
        """process_query_with_trace also returns clarification when confidence is low."""
        low = CLARIFICATION_THRESHOLD - 0.05
        llm = mock_llm(f'{{"domain": "sales", "confidence": {low}, "reasoning": "unclear"}}')
        with patch("app.agents.router.get_llm", return_value=llm):
            result = orchestrator.process_query_with_trace("xyzzy plugh frobozz")
        assert result.get("needs_clarification") is True
        # Routing step must still be recorded in the trace
        assert any(s["step"] == "routing" for s in result.get("steps", []))

    def test_keyword_no_match_triggers_clarification(self, orchestrator):
        """Keyword router's 0.33 default (no keywords matched) triggers clarification."""
        with patch("app.agents.router.get_llm", return_value=None):
            result = orchestrator.process_query("xyzzy plugh frobozz")
        assert result.get("needs_clarification") is True


# ---------------------------------------------------------------------------
# Shared LLM client singleton
# ---------------------------------------------------------------------------

class TestSharedLLMClientSingleton:
    """get_llm() returns one shared instance; reset_llm_client() allows re-init.

    These tests inject directly into the module-level variables rather than
    patching langchain_openai (which is not installed in the test environment).
    """

    def test_same_instance_on_repeated_calls(self):
        """Two calls to get_llm() return the same object once initialized."""
        import app.agents.llm_client as llm_mod
        from app.agents.llm_client import get_llm
        # Pre-seed the singleton so get_llm() skips real initialization
        fake = MagicMock()
        llm_mod._client = fake
        llm_mod._init_attempted = True
        assert get_llm() is fake
        assert get_llm() is fake  # second call returns the exact same instance

    def test_returns_none_when_api_key_not_set(self):
        """get_llm() returns None in the test environment (no API key, no package)."""
        from app.agents.llm_client import get_llm
        # The autouse fixture already reset the singleton; calling get_llm() with
        # no key configured (test env) and no langchain_openai installed → None.
        result = get_llm()
        assert result is None

    def test_reset_allows_reinitialization(self):
        """After reset_llm_client(), get_llm() can return a new instance."""
        import app.agents.llm_client as llm_mod
        from app.agents.llm_client import get_llm, reset_llm_client

        fake1 = MagicMock()
        llm_mod._client = fake1
        llm_mod._init_attempted = True
        assert get_llm() is fake1

        reset_llm_client()

        fake2 = MagicMock()
        llm_mod._client = fake2
        llm_mod._init_attempted = True
        assert get_llm() is fake2
        assert fake1 is not fake2
