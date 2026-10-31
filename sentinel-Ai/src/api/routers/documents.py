"""
POST /v1/documents/analyze
    Accepts DocumentApiRequest from Spring Boot.
    Translates → DocumentAnalysisRequest → invokes graph → DocumentApiResponse.

POST /v1/documents/upload
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
from src.api.rate_limit import enforce_document_rate_limit, enforce_knowledge_rate_limit
from src.api.schemas.requests import DocumentApiRequest, KnowledgeApiRequest
from src.api.schemas.responses import DocumentApiResponse, ErrorApiResponse, KnowledgeApiResponse
from src.api.security import require_service_token
from src.common.models import FileMetadata
from src.orchestration.models import DocumentAnalysisRequest, KnowledgeUploadRequest, WorkflowType


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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post(
    "/analyze",
    response_model=DocumentApiResponse,
    summary="Analyze a document through the security pipeline",
    dependencies=[
        Depends(require_service_token),
        Depends(enforce_document_rate_limit),
    ],
)
async def handle_document_analysis(
    body: DocumentApiRequest,
    graph: Annotated[CompiledStateGraph, Depends(get_compiled_graph)],
) -> DocumentApiResponse:
    """
    Translate DocumentApiRequest → DocumentAnalysisRequest
    → invoke graph → DocumentApiResponse.
    """
    # Fix: "filename" is a reserved LogRecord attribute — use "document_filename".
    logger.info(
        "document analysis request received",
        extra={
            "request_id": body.request_id,
            "user_id": body.user_id,
            "document_filename": body.filename,
        },
    )

    # FIX 8A — Server-side file size enforcement (10 MB hard limit).
    _MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    if body.size_bytes > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10MB.",
        )

    # FIX 8B — File path traversal validation.
    import tempfile
    _resolved = Path(body.file_path).resolve()
    _allowed_roots = [
        Path(tempfile.gettempdir()).resolve(),
    ]
    if not any(str(_resolved).startswith(str(root)) for root in _allowed_roots):
        logger.warning(
            "Path traversal attempt detected: %s request_id=%s",
            body.file_path,
            body.request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
        )

    metadata = FileMetadata(
        filename=body.filename,
        extension=body.extension,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        checksum=body.checksum,
    )

    doc_request = DocumentAnalysisRequest(
        workflow=WorkflowType.DOCUMENT_ANALYSIS,
        request_id=body.request_id,
        file_path=Path(body.file_path),
        metadata=metadata,
    )

    try:
        initial_state = {
            "request_id": doc_request.request_id,
            "workflow": doc_request.workflow.value,
            "user_id": body.user_id,
            "session_id": None,
            "query": None,
            "file_path": doc_request.file_path,
            "metadata": doc_request.metadata,
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

        # Fix: MemorySaver checkpointer requires thread_id in config.
        config = {"configurable": {"thread_id": doc_request.request_id}}
        result_state: dict = graph.invoke(initial_state, config)

    except Exception as exc:
        logger.exception(
            "graph invocation failed for document analysis",
            extra={"request_id": body.request_id, "user_id": body.user_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorApiResponse(
                request_id=body.request_id,
                error_code="GRAPH_INVOCATION_FAILED",
                message="Internal AI engine error.",
                workflow=WorkflowType.DOCUMENT_ANALYSIS.value,
            ).model_dump(),
        ) from exc

    error_msg: str | None = result_state.get("error")
    final_response = result_state.get("final_response")

    if error_msg:
        logger.error(
            "graph returned error for document analysis",
            extra={"request_id": body.request_id, "error": error_msg},
        )
        return DocumentApiResponse(
            request_id=body.request_id,
            success=False,
            message=error_msg,
            analysis_result=None,
        )

    logger.info(
        "document analysis succeeded",
        extra={"request_id": body.request_id, "user_id": body.user_id},
    )
    return DocumentApiResponse(
        request_id=body.request_id,
        success=True,
        message="Document analyzed successfully.",
        analysis_result=final_response,
    )


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

    This endpoint is the target of Spring Boot's FastApiClient.uploadDocument()
    which calls POST /v1/documents/upload.
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

    # FIX 8A — Server-side file size enforcement (10 MB hard limit).
    _MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    if body.size_bytes > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10MB.",
        )

    # FIX 8B — File path traversal validation.
    import tempfile
    _resolved = Path(body.file_path).resolve()
    _allowed_roots = [
        Path(tempfile.gettempdir()).resolve(),
    ]
    if not any(str(_resolved).startswith(str(root)) for root in _allowed_roots):
        logger.warning(
            "Path traversal attempt detected: %s request_id=%s",
            body.file_path,
            body.request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path.",
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
            "retrieved_chunks": None,
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
            extra={
                "request_id": body.request_id,
                "user_id": body.user_id,
                "error": error_msg,
            },
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