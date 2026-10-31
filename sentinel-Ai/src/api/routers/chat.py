"""
POST /v1/chat
Accepts ChatApiRequest from Spring Boot.
Translates → ChatRequest → invokes graph → translates → ChatApiResponse.
Service-token auth + per-user rate limit. No persistence. No business logic.
"""

from __future__ import annotations
from fastapi.responses import JSONResponse

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from langgraph.graph.state import CompiledStateGraph

from src.api.dependencies import get_compiled_graph
from src.api.rate_limit import enforce_chat_rate_limit
from src.api.schemas.requests import ChatApiRequest
from src.api.schemas.responses import ChatApiResponse, ErrorApiResponse
from src.api.security import require_service_token
from src.orchestration.models import ChatRequest, WorkflowType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatApiResponse,
    summary="Execute a chat request through the LangGraph pipeline",
    dependencies=[
        Depends(require_service_token),
        Depends(enforce_chat_rate_limit),
    ],
)
async def handle_chat(
    body: ChatApiRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_compiled_graph)],
) -> ChatApiResponse:
    """
    Translate ChatApiRequest → ChatRequest → invoke graph → ChatApiResponse.

    Blocked requests return HTTP 200 with success=False and blocked=True.
    HTTP 4xx/5xx are reserved for infrastructure failures only.
    """
    logger.info(
        "chat request received",
        extra={"request_id": body.request_id, "user_id": body.user_id},
    )

    chat_request = ChatRequest(
        workflow=WorkflowType.CHAT,
        request_id=body.request_id,
        query=body.query,
        session_id=body.session_id,
    )

    try:
        initial_state = {
            "request_id": chat_request.request_id,
            "workflow": chat_request.workflow.value,
            "user_id": body.user_id,
            "query": chat_request.query,
            "session_id": chat_request.session_id,
            "file_path": None,
            "metadata": None,
            "security_passed": None,
            "normalized_query": None,
            "risk_score": None,
            "blocked": None,
            "raw_response": None,
            "retrieved_chunks": None,
            "validation_approved": None,
            "final_response": None,
            "error": None,
        }

        result_state: dict = graph.invoke(
            initial_state,
            config={
                "configurable": {
                    "thread_id": chat_request.session_id or chat_request.request_id
                }
            },
        )
        raw_res = result_state.get("raw_response")
        final_res = result_state.get("final_response")
        raw_len = len(raw_res) if isinstance(raw_res, (str, list, dict)) else None
        final_len = len(final_res) if isinstance(final_res, (str, list, dict)) else None

        logger.info(
            "graph result_state — request_id=%s user_id=%s raw_len=%s final_len=%s "
            "validation_approved=%r error=%r",
            chat_request.request_id,
            body.user_id,
            raw_len,
            final_len,
            result_state.get("validation_approved"),
            result_state.get("error"),
        )

    except Exception:
        logger.exception(
            "graph invocation failed for chat",
            extra={"request_id": body.request_id, "user_id": body.user_id},
        )

        return JSONResponse(
            status_code=500,
            content=ErrorApiResponse(
                request_id=body.request_id,
                success=False,
                error_code="GRAPH_INVOCATION_FAILED",
                message="Internal AI engine error.",
                workflow=WorkflowType.CHAT.value,
            ).model_dump(),
        )

    blocked: bool = bool(result_state.get("blocked")) or (
        result_state.get("validation_approved") is False
    )
    final_response = result_state.get("final_response")
    error_msg: str | None = result_state.get("error")

    # Blocked path — security rejected the request
    if blocked:
        risk_score = result_state.get("risk_score")
        reason = (
            final_response.get("reason", "Blocked by security policy.")
            if isinstance(final_response, dict)
            else (
                final_response
                if isinstance(final_response, str) and final_response
                else "Blocked by security policy."
            )
        )
        logger.warning(
            "chat request blocked",
            extra={
                "request_id": body.request_id,
                "user_id": body.user_id,
                "risk_score": risk_score,
            },
        )
        return ChatApiResponse(
            request_id=body.request_id,
            success=False,
            message=reason,
            response_text=None,
            blocked=True,
            risk_score=risk_score,
        )

    # Error path — graph set error without blocking
    if error_msg:
        logger.error(
            "graph returned error state",
            extra={
                "request_id": body.request_id,
                "user_id": body.user_id,
                "error": error_msg,
            },
        )
        return ChatApiResponse(
            request_id=body.request_id,
            success=False,
            message=error_msg,
            response_text=None,
            blocked=False,
            risk_score=result_state.get("risk_score"),
        )

    # Success path
    response_text: str | None = (
        final_response
        if isinstance(final_response, str)
        else str(final_response)
        if final_response is not None
        else None
    )

    logger.info(
        "chat request succeeded",
        extra={"request_id": body.request_id, "user_id": body.user_id},
    )
    return ChatApiResponse(
        request_id=body.request_id,
        success=True,
        message="Response generated successfully.",
        response_text=response_text,
        blocked=False,
        risk_score=result_state.get("risk_score"),
    )
