"""
LangGraph node functions for the Sentinel AI Engine workflow.

Each node is a pure function with the signature:

    (state: SentinelState) -> SentinelState

Nodes are thin adapters. They translate state fields into agent method
arguments, invoke exactly one agent method, and write the result back
into state. No business logic, branching, or agent-to-agent calls
belong here.

Dependency Injection
--------------------
Nodes do not instantiate agents. Agent instances are injected at graph
construction time via factory closures (see graph.py). Each public
function in this module is a factory that returns the actual node
callable with the agent pre-bound.

Agent Execution Contract
------------------------
- security_node      : calls InputSecurityAgent.analyze() for chat only.
                       Non-chat workflows are passed through immediately.
                       This mirrors SentinelOrchestrator which only runs
                       InputSecurityAgent for CHAT requests.
- chat_generation_node: calls AssistantAgent.generate_response()
- validation_node    : calls OutputValidationAgent.validate()
- document_analysis_node: calls AssistantAgent.analyze_document()
- knowledge_upload_node : calls AssistantAgent.upload_document()
- blocked_node       : pure state transformation, no agent call

The AssistantAgent injected here MUST be constructed without its own
security_agent or output_validation_agent. The orchestration layer
owns those boundaries. See OrchestratorFactory for the correct
construction pattern.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from src.assistant_agent.assistant_agent import AssistantAgent
from src.input_security_agent.input_security_agent import InputSecurityAgent
from src.input_security_agent.models import SecurityContext
from src.output_validation_agent.output_validation_agent import OutputValidationAgent
from src.output_validation_agent.models import ValidationContext

from .state import SentinelState

logger = logging.getLogger(__name__)

# WorkflowType string value for chat — must match WorkflowType.CHAT StrEnum
_WORKFLOW_CHAT = "chat"


# ---------------------------------------------------------------------------
# Node factory: security_node
# ---------------------------------------------------------------------------

def make_security_node(
    agent: InputSecurityAgent,
) -> Callable[[SentinelState], SentinelState]:
    """
    Return a security node that invokes InputSecurityAgent.analyze().

    InputSecurityAgent is a query-level guard. It is only meaningful
    when a user query exists — i.e. the chat workflow. Document analysis
    and knowledge upload workflows carry no user query. Running the agent
    with an empty string is semantically incorrect and will crash the
    semantic similarity detector (embed_query rejects empty input).

    This matches SentinelOrchestrator which only calls InputSecurityAgent
    inside _execute_chat(), never inside _execute_document_analysis() or
    _execute_knowledge_upload().

    The node populates:
        - security_passed
        - normalized_query
        - risk_score
        - blocked

    Parameters
    ----------
    agent:
        A fully constructed InputSecurityAgent instance.
    """

    def security_node(state: SentinelState) -> SentinelState:

        # ------------------------------------------------------------------
        # Non-chat workflows have no user query.
        # InputSecurityAgent must not be invoked — pass through immediately.
        # This matches SentinelOrchestrator._execute_document_analysis() and
        # _execute_knowledge_upload() which skip InputSecurityAgent entirely.
        # ------------------------------------------------------------------

        workflow = state.get("workflow", "")

        if workflow != _WORKFLOW_CHAT:
            logger.info(
                "security_node: workflow='%s' has no user query — "
                "bypassing InputSecurityAgent. request_id=%s",
                workflow,
                state.get("request_id"),
            )
            return {
                **state,
                "security_passed": True,
                "normalized_query": None,
                "risk_score": 0.0,
                "blocked": False,
            }

        # ------------------------------------------------------------------
        # Chat workflow: run full input security analysis.
        # ------------------------------------------------------------------

        query = state.get("query") or ""

        logger.info(
            "security_node: starting input security analysis. "
            "request_id=%s",
            state.get("request_id"),
        )

        try:
            context = SecurityContext(query=query)
            decision = agent.analyze(context)

        except Exception:
            logger.exception(
                "security_node: InputSecurityAgent.analyze() raised an "
                "unhandled exception. request_id=%s",
                state.get("request_id"),
            )
            return {
                **state,
                "security_passed": False,
                "normalized_query": query,
                "risk_score": 1.0,
                "blocked": True,
                "error": "Input security analysis failed due to an internal error.",
            }

        passed = decision.allowed
        risk = decision.risk_assessment.risk_score

        logger.info(
            "security_node: analysis complete. "
            "allowed=%s risk_score=%.2f request_id=%s",
            passed,
            risk,
            state.get("request_id"),
        )

        if not passed:
            logger.warning(
                "security_node: query blocked. "
                "risk_score=%.2f request_id=%s",
                risk,
                state.get("request_id"),
            )

        return {
            **state,
            "security_passed": passed,
            "normalized_query": decision.normalized_context,
            "risk_score": risk,
            "blocked": not passed,
        }

    return security_node


# ---------------------------------------------------------------------------
# Node factory: chat_generation_node
# ---------------------------------------------------------------------------

def make_chat_generation_node(
    agent: AssistantAgent,
) -> Callable[[SentinelState], SentinelState]:
    """
    Return a node that invokes AssistantAgent.generate_response().

    Reads:
        - normalized_query

    Populates:
        - raw_response
        - retrieved_chunks

    On failure, sets blocked=True so the conditional edge in graph.py
    routes to blocked_node instead of validation_node. This prevents
    validation_node from receiving an empty raw_response, which would
    cause HallucinationValidator to raise ValidatorExecutionError.

    Parameters
    ----------
    agent:
        AssistantAgent constructed WITHOUT security_agent and
        WITHOUT output_validation_agent. The orchestration layer
        owns both boundaries.
    """

    def chat_generation_node(state: SentinelState) -> SentinelState:
        normalized_query = state.get("normalized_query") or ""
        user_id = state.get("user_id")

        logger.info(
            "chat_generation_node: invoking AssistantAgent.generate_response(). "
            "request_id=%s user_id=%s",
            state.get("request_id"),
            user_id,
        )

        # Tenant scope: user's uploads + shared domain packs (domain != uploaded).
        metadata_filter = None
        if user_id:
            metadata_filter = {
                "$or": [
                    {"user_id": user_id},
                    {"domain": {"$ne": "uploaded"}},
                ]
            }

        # FIX 5C — Wrap LLM/agent call in try/except. On any exception:
        # log with logger.error, set final_response to safe string,
        # do NOT set blocked=True (this is not a security event).
        try:
            raw_response, retrieved_chunks = agent.generate_response(
                query=normalized_query,
                metadata_filter=metadata_filter,
            )

        except Exception as exc:
            logger.error(
                "chat_generation_node: generate_response() raised an "
                "unhandled exception. %s: %s request_id=%s",
                type(exc).__name__,
                exc,
                state.get("request_id"),
            )
            return {
                **state,
                "raw_response": None,
                "retrieved_chunks": [],
                "blocked": False,
                "final_response": (
                    "I was unable to process your request. Please try again."
                ),
                "error": "Response generation failed due to an internal error.",
            }

        logger.info(
            "chat_generation_node: response generated successfully. "
            "request_id=%s",
            state.get("request_id"),
        )

        return {
            **state,
            "raw_response": raw_response,
            "retrieved_chunks": retrieved_chunks,
        }

    return chat_generation_node



# ---------------------------------------------------------------------------
# Node factory: validation_node
# ---------------------------------------------------------------------------

def make_validation_node(
    agent: Optional[OutputValidationAgent],
) -> Callable[[SentinelState], SentinelState]:
    """
    Return a node that invokes OutputValidationAgent.validate().

    Reads:
        - normalized_query
        - raw_response
        - retrieved_chunks
        - request_id

    Populates:
        - validation_approved
        - final_response

    Parameters
    ----------
    agent:
        Optional OutputValidationAgent. If None, validation is skipped.
    """

    def validation_node(state: SentinelState) -> SentinelState:
        raw_response = state.get("raw_response") or ""
        normalized_query = state.get("normalized_query") or ""
        request_id = state.get("request_id", "")
        retrieved_chunks = state.get("retrieved_chunks") or []

        if agent is None:
            logger.debug(
                "validation_node: OutputValidationAgent not configured. "
                "Passing raw_response through. request_id=%s",
                request_id,
            )
            return {
                **state,
                "validation_approved": True,
                "final_response": raw_response,
            }

        logger.info(
            "validation_node: invoking OutputValidationAgent.validate(). "
            "request_id=%s",
            request_id,
        )

        try:
            context = ValidationContext(
                user_query=normalized_query,
                llm_response=raw_response,
                retrieved_chunks=retrieved_chunks,
                metadata={"request_id": request_id},
            )
            decision = agent.validate(context)

        except Exception:
            logger.exception(
                "validation_node: OutputValidationAgent.validate() raised "
                "an unhandled exception. request_id=%s",
                request_id,
            )
            return {
                **state,
                "validation_approved": False,
                "final_response": raw_response,
                "error": "Output validation failed due to an internal error.",
            }

        if not decision.approved:
            violated_categories = [
                r.category.value if hasattr(r.category, "value") else str(r.category)
                for r in getattr(decision, "validation_results", [])
                if not getattr(r, "passed", True)
            ]
            logger.warning(
                "validation_node: output validation rejected response. "
                "request_id=%s categories=%s",
                request_id,
                violated_categories,
            )
            return {
                **state,
                "blocked": True,
                "validation_approved": False,
                "final_response": "The response was withheld because it violated output policy.",
                "error": "Output policy violation.",
            }

        logger.info(
            "validation_node: validation complete. "
            "approved=%s request_id=%s",
            decision.approved,
            request_id,
        )

        return {
            **state,
            "validation_approved": decision.approved,
            "final_response": decision.final_response,
        }

    return validation_node


# ---------------------------------------------------------------------------
# Node factory: document_analysis_node
# ---------------------------------------------------------------------------

def make_document_analysis_node(
    agent: AssistantAgent,
) -> Callable[[SentinelState], SentinelState]:
    """
    Return a node that invokes AssistantAgent.analyze_document().

    Reads:
        - file_path
        - metadata

    Populates:
        - final_response

    Parameters
    ----------
    agent:
        AssistantAgent with DocumentSecurityAgent injected.
    """

    def document_analysis_node(state: SentinelState) -> SentinelState:
        file_path = state.get("file_path")
        metadata = state.get("metadata")

        logger.info(
            "document_analysis_node: invoking AssistantAgent.analyze_document(). "
            "request_id=%s",
            state.get("request_id"),
        )

        try:
            result = agent.analyze_document(
                file_path=file_path,
                metadata=metadata,
            )

        except Exception:
            logger.exception(
                "document_analysis_node: analyze_document() raised an "
                "unhandled exception. request_id=%s",
                state.get("request_id"),
            )
            return {
                **state,
                "blocked": True,
                "final_response": None,
                "error": "Document analysis failed due to an internal error.",
            }

        logger.info(
            "document_analysis_node: document analysis completed. "
            "request_id=%s",
            state.get("request_id"),
        )

        return {
            **state,
            "final_response": result,
        }

    return document_analysis_node


# ---------------------------------------------------------------------------
# Node factory: knowledge_upload_node
# ---------------------------------------------------------------------------

def make_knowledge_upload_node(
    agent: AssistantAgent,
) -> Callable[[SentinelState], SentinelState]:
    """
    Return a node that invokes AssistantAgent.upload_document().

    Reads:
        - file_path
        - metadata

    Populates:
        - final_response

    Parameters
    ----------
    agent:
        AssistantAgent with DocumentSecurityAgent and
        KnowledgeIngestionPipeline injected.
    """

    def knowledge_upload_node(state: SentinelState) -> SentinelState:
        file_path = state.get("file_path")
        metadata = state.get("metadata")
        user_id = state.get("user_id")

        logger.info(
            "knowledge_upload_node: invoking AssistantAgent.upload_document(). "
            "request_id=%s user_id=%s",
            state.get("request_id"),
            user_id,
        )

        try:
            result = agent.upload_document(
                file_path=file_path,
                metadata=metadata,
                user_id=user_id,
            )

        except Exception:
            logger.exception(
                "knowledge_upload_node: upload_document() raised an "
                "unhandled exception. request_id=%s",
                state.get("request_id"),
            )
            return {
                **state,
                "blocked": True,
                "final_response": None,
                "error": "Knowledge upload failed due to an internal error.",
            }

        logger.info(
            "knowledge_upload_node: upload completed successfully. "
            "request_id=%s",
            state.get("request_id"),
        )

        return {
            **state,
            "final_response": result,
        }

    return knowledge_upload_node


# ---------------------------------------------------------------------------
# blocked_node — no agent call, pure state transformation
# ---------------------------------------------------------------------------

def blocked_node(state: SentinelState) -> SentinelState:
    """
    Terminal node for blocked or errored requests.

    Constructs a structured final_response dict that mirrors the
    blocked SentinelResponse.data produced by the existing orchestrator,
    ensuring the graph exit contract is identical to the current behaviour.

    Reads:
        - risk_score
        - error

    Populates:
        - final_response
        - blocked (ensures True)
    """

    risk_score = state.get("risk_score") or 0.0
    error_message = state.get("error")

    logger.warning(
        "blocked_node: request terminated early. "
        "risk_score=%.2f error=%s request_id=%s",
        risk_score,
        error_message,
        state.get("request_id"),
    )

    final_response = {
    "blocked": True,
    "reason": error_message or "Input security policy violation.",
    "risk_level": "HIGH" if risk_score >= 0.7 else "MEDIUM",
    }

    return {
        **state,
        "blocked": True,
        "final_response": final_response,
    }