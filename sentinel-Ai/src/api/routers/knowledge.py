"""
POST /v1/knowledge/upload
Accepts KnowledgeApiRequest from Spring Boot.
Translates → KnowledgeUploadRequest → invokes graph → KnowledgeApiResponse.
Service-token auth + per-user rate limit. No persistence. No business logic.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.graph.state import CompiledStateGraph

from src.api.dependencies import get_compiled_graph
from src.api.rate_limit import enforce_knowledge_rate_limit
from src.api.schemas.requests import KnowledgeApiRequest
from src.api.schemas.responses import ErrorApiResponse, KnowledgeApiResponse
from src.api.security import require_service_token
from src.common.models import FileMetadata
from src.orchestration.models import KnowledgeUploadRequest, WorkflowType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


def _to_jsonable(value: Any) -> Any:
    """Convert dataclasses / enums from LangGraph state into plain JSON data."""
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        return {
            key: _to_jsonable(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


@router.post(
    "/upload",
    response_model=KnowledgeApiResponse,
    summary="Ingest a document into the knowledge base",
    dependencies=[
        Depends(require_service_token),
        Depends(enforce_knowledge_rate_limit),
    ],
)
async def handle_knowledge_upload(
    body: KnowledgeApiRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_compiled_graph)],
) -> KnowledgeApiResponse:
    """
    Translate KnowledgeApiRequest → KnowledgeUploadRequest
    → invoke graph → KnowledgeApiResponse.
    """
    # Fix: "filename" is a reserved LogRecord attribute — use "document_filename".
    logger.info(
        "knowledge upload request received",
        extra={
            "request_id": body.request_id,
            "user_id": body.user_id,
            "document_filename": body.filename,
        },
    )

    metadata = FileMetadata(
        filename=body.filename,
        extension=body.extension,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        checksum=body.checksum,
    )

    upload_request = KnowledgeUploadRequest(
        workflow=WorkflowType.KNOWLEDGE_UPLOAD,
        request_id=body.request_id,
        file_path=Path(body.file_path),
        metadata=metadata,
    )

    try:
        initial_state = {
            "request_id": upload_request.request_id,
            "workflow": upload_request.workflow.value,
            "user_id": body.user_id,
            "session_id": None,
            "query": None,
            "file_path": upload_request.file_path,
            "metadata": upload_request.metadata,
            "security_passed": None,
            "normalized_query": None,
            "risk_score": None,
            "blocked": None,
            "raw_response": None,
            "validation_approved": None,
            "final_response": None,
            "error": None,
        }

        # Fix: MemorySaver checkpointer requires thread_id in config.
        config = {"configurable": {"thread_id": upload_request.request_id}}
        result_state: dict = graph.invoke(initial_state, config)

    except Exception as exc:
        logger.exception(
            "graph invocation failed for knowledge upload",
            extra={"request_id": body.request_id, "user_id": body.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorApiResponse(
                request_id=body.request_id,
                error_code="GRAPH_INVOCATION_FAILED",
                message="Internal AI engine error.",
                workflow=WorkflowType.KNOWLEDGE_UPLOAD.value,
            ).model_dump(),
        ) from exc

    error_msg: str | None = result_state.get("error")
    final_response = result_state.get("final_response")

    if error_msg:
        logger.error(
            "graph returned error for knowledge upload",
            extra={"request_id": body.request_id, "error": error_msg},
        )
        return KnowledgeApiResponse(
            request_id=body.request_id,
            success=False,
            message=error_msg,
            ingestion_result=None,
        )

    logger.info(
        "knowledge upload succeeded",
        extra={"request_id": body.request_id, "user_id": body.user_id},
    )
    return KnowledgeApiResponse(
        request_id=body.request_id,
        success=True,
        message="Document ingested into knowledge base successfully.",
        ingestion_result=_to_jsonable(final_response),
    )