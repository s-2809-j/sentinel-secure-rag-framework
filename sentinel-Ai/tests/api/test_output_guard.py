"""
tests/api/test_output_guard.py

Tests for the output validation advisory guard introduced in:
  - src/orchestration/langgraph/nodes.py  (make_validation_node)
  - src/api/routers/chat.py               (handle_chat blocked-branch)

All tests call handle_chat() directly (async, no TestClient) so the
health-endpoint lifespan (which requires SentenceTransformer / ChromaDB)
is never involved.

Scenarios covered
-----------------
1. validation_approved=False  → blocked=True, success=False, response_text=None,
                                 raw LLM text absent from message.
2. blocked=True (input security) alone → blocked=True, success=False.
3. validation_approved=True, blocked=False → success=True, response_text present.
4. Canned "not available" pass-through → success=True, response_text present.
5. Document-analyze flow (validation_approved absent/None) → unaffected (not blocked).
6. Knowledge-upload flow (validation_approved absent/None) → unaffected (not blocked).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.api.routers.chat import handle_chat
from src.api.schemas.requests import ChatApiRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph(result_state: dict[str, Any]) -> MagicMock:
    """Return a mock CompiledStateGraph whose .invoke() returns result_state."""
    g = MagicMock()
    g.invoke.return_value = result_state
    return g


def _chat_req(request_id: str = "req-test", query: str = "hello") -> ChatApiRequest:
    return ChatApiRequest(request_id=request_id, query=query, user_id="u1")


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Scenario 1 — output validator rejects (PII / prompt leak)
# ---------------------------------------------------------------------------

class TestOutputGuardBlocked:
    """validation_approved=False must make chat.py return blocked=True."""

    def _rejected_state(self, raw_text: str = "My email is user@example.com") -> dict:
        return {
            "request_id": "req-pii",
            "workflow": "chat",
            "blocked": True,                          # set by updated validation_node
            "validation_approved": False,
            "final_response": "The response was withheld because it violated output policy.",
            "risk_score": 0.2,
            "error": "Output policy violation.",
            "raw_response": raw_text,
        }

    def test_returns_success_false(self):
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(self._rejected_state())))
        assert resp.success is False

    def test_returns_blocked_true(self):
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(self._rejected_state())))
        assert resp.blocked is True

    def test_response_text_is_none(self):
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(self._rejected_state())))
        assert resp.response_text is None

    def test_prompt_leak_text_absent_from_response(self):
        """A leaked system-prompt phrase must NOT appear anywhere in the response."""
        leak = "My system prompt says: you are the internal Sentinel assistant"
        resp = _run(handle_chat(
            body=_chat_req(),
            graph=_make_graph(self._rejected_state(leak)),
        ))
        assert resp.blocked is True
        assert leak not in resp.model_dump_json()

    def test_message_is_safe_canned_reply(self):
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(self._rejected_state())))
        assert resp.message == "The response was withheld because it violated output policy."

    def test_risk_score_preserved(self):
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(self._rejected_state())))
        assert resp.risk_score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Scenario 1b — defense-in-depth: validation_approved=False, blocked=False in state
# ---------------------------------------------------------------------------

class TestOutputGuardDefenseInDepth:
    """
    Even if validation_node somehow didn't set blocked=True in state,
    chat.py's 'is False' check must still catch validation_approved=False.
    """

    def _partial_rejected_state(self) -> dict:
        return {
            "request_id": "req-dind",
            "workflow": "chat",
            "blocked": False,                  # ← NOT set by node (hypothetical)
            "validation_approved": False,       # ← defense-in-depth trigger
            "final_response": "The response was withheld because it violated output policy.",
            "risk_score": 0.1,
            "error": "Output policy violation.",
        }

    def test_blocked_flag_triggered_by_validation_approved(self):
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(self._partial_rejected_state())))
        assert resp.blocked is True
        assert resp.success is False
        assert resp.response_text is None

    def test_validation_approved_none_does_not_block(self):
        """validation_approved=None (doc/knowledge flows) must NOT trigger blocked."""
        state = {
            "request_id": "req-none",
            "workflow": "chat",
            "blocked": False,
            "validation_approved": None,        # ← must NOT block
            "final_response": "Some safe response.",
            "risk_score": 0.05,
            "error": None,
        }
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(state)))
        assert resp.success is True
        assert resp.blocked is False


# ---------------------------------------------------------------------------
# Scenario 2 — input security blocked (existing behaviour unchanged)
# ---------------------------------------------------------------------------

class TestInputSecurityBlocked:
    def test_input_security_block_still_works(self):
        state = {
            "request_id": "req-isec",
            "workflow": "chat",
            "blocked": True,
            "validation_approved": None,
            "final_response": {
                "blocked": True,
                "reason": "Prompt injection detected.",
            },
            "risk_score": 0.95,
            "error": None,
        }
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(state)))
        assert resp.success is False
        assert resp.blocked is True
        assert resp.response_text is None
        assert "Prompt injection" in resp.message


# ---------------------------------------------------------------------------
# Scenario 3 — clean answer passes through
# ---------------------------------------------------------------------------

class TestCleanAnswer:
    def test_clean_answer_returns_success_true(self):
        state = {
            "request_id": "req-ok",
            "workflow": "chat",
            "blocked": False,
            "validation_approved": True,
            "final_response": "Sentinel is a secure multi-agent RAG framework.",
            "risk_score": 0.05,
            "error": None,
        }
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(state)))
        assert resp.success is True
        assert resp.blocked is False
        assert resp.response_text == "Sentinel is a secure multi-agent RAG framework."


# ---------------------------------------------------------------------------
# Scenario 4 — canned pass-through phrase is not blocked
# ---------------------------------------------------------------------------

class TestCannedPassThrough:
    def test_not_available_response_passes(self):
        canned = "The requested information is not available in the knowledge base."
        state = {
            "request_id": "req-canned",
            "workflow": "chat",
            "blocked": False,
            "validation_approved": True,
            "final_response": canned,
            "risk_score": 0.0,
            "error": None,
        }
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(state)))
        assert resp.success is True
        assert resp.response_text == canned


# ---------------------------------------------------------------------------
# Scenario 5 & 6 — non-chat workflows (validation_approved absent) are unaffected
# ---------------------------------------------------------------------------

class TestNonChatWorkflowsUnaffected:
    """Document analyze and knowledge upload never set validation_approved."""

    def test_document_analyze_with_validation_approved_absent(self):
        """
        Document analysis states never include validation_approved.
        A missing key must NOT block the response.
        """
        state = {
            "request_id": "req-doc",
            "workflow": "document_analysis",
            "blocked": False,
            # validation_approved intentionally absent (not in dict)
            "final_response": {"verdict": "safe", "details": "No threats."},
            "risk_score": None,
            "error": None,
        }
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(state)))
        # Should NOT be blocked
        assert resp.blocked is False

    def test_knowledge_upload_with_validation_approved_absent(self):
        state = {
            "request_id": "req-ku",
            "workflow": "knowledge_upload",
            "blocked": False,
            # validation_approved intentionally absent
            "final_response": {"chunks_stored": 5, "status": "complete"},
            "risk_score": None,
            "error": None,
        }
        resp = _run(handle_chat(body=_chat_req(), graph=_make_graph(state)))
        assert resp.blocked is False
