"""
SentinelState — the single shared state object for the LangGraph workflow.

Every node in the Sentinel LangGraph reads from and writes to this TypedDict.
No node communicates with another node directly. All inter-node communication
is mediated exclusively through this state contract.

Design Principles
-----------------
- Every field is Optional where the node that populates it has not yet run.
- Fields are grouped by the pipeline stage that owns them.
- No agent instances, callables, or mutable objects are stored in state.
- This module has zero dependencies on LangGraph internals — it is a pure
  Python TypedDict, importable independently for testing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from typing_extensions import TypedDict

from src.common.models import FileMetadata
from src.knowledge_base.models import RetrievedChunk


class SentinelState(TypedDict):
    """
    Complete shared state for a single Sentinel LangGraph workflow execution.

    Lifecycle
    ---------
    The state is populated incrementally as nodes execute:

        START
          │ workflow, query/file_path/metadata, request_id
          ▼
        security_node
          │ security_passed, normalized_query, risk_score, blocked
          ▼
        [routing]
          │
          ├── blocked_node          → final_response, error
          ├── knowledge_upload_node → final_response
          ├── document_analysis_node→ final_response
          └── chat_generation_node
                │ raw_response, retrieved_chunks
                ▼
              validation_node       → validation_approved, final_response
    """

    # ------------------------------------------------------------------
    # Request identity
    # ------------------------------------------------------------------

    request_id: str
    """Correlation identifier copied from BaseRequest.request_id."""

    workflow: str
    """
    Workflow type string. One of: 'chat', 'document_analysis',
    'knowledge_upload'. Matches WorkflowType StrEnum values directly.
    """

    user_id: Optional[str]
    """
    Authenticated user UUID asserted by Spring Boot.
    Used for audit logging and knowledge-base tenant scoping.
    """

    session_id: Optional[str]
    """
    Conversation thread id for chat workflows (LangGraph checkpointer).
    None for document workflows.
    """

    # ------------------------------------------------------------------
    # Chat workflow input
    # ------------------------------------------------------------------

    query: Optional[str]
    """
    Original user query for chat workflows.
    None for document workflows.
    """

    # ------------------------------------------------------------------
    # Document / knowledge workflow input
    # ------------------------------------------------------------------

    file_path: Optional[Path]
    """
    Absolute path to the document being analyzed or ingested.
    None for chat workflows.
    """

    metadata: Optional[FileMetadata]
    """
    Document metadata forwarded from the originating FileRequest.
    None for chat workflows.
    """

    # ------------------------------------------------------------------
    # Security node outputs
    # ------------------------------------------------------------------

    security_passed: Optional[bool]
    """
    True if InputSecurityAgent approved the query.
    Populated by security_node.
    """

    normalized_query: Optional[str]
    """
    Query after InputNormalizer processing.
    Used by chat_generation_node instead of the raw query.
    Populated by security_node.
    """

    risk_score: Optional[float]
    """
    Risk score produced by RiskScoringEngine.
    Carried in state for audit/logging purposes.
    Populated by security_node.
    """

    blocked: Optional[bool]
    """
    True when the request must be terminated early — either because
    InputSecurityAgent rejected the query or an unrecoverable error
    occurred in a node.
    Populated by security_node or any node that sets an error.
    """

    # ------------------------------------------------------------------
    # Chat generation node outputs
    # ------------------------------------------------------------------

    raw_response: Optional[str]
    """
    Raw LLM response string from AssistantAgent.generate_response().
    Populated by chat_generation_node.
    Consumed by validation_node.
    """

    retrieved_chunks: Optional[list[RetrievedChunk]]
    """
    Chunks retrieved from the knowledge base during generate_response().
    Populated by chat_generation_node.
    Consumed by validation_node to run HallucinationValidator.
    None for non-chat workflows.
    """

    # ------------------------------------------------------------------
    # Output validation node outputs
    # ------------------------------------------------------------------

    validation_approved: Optional[bool]
    """
    True if OutputValidationAgent approved the raw response.
    Populated by validation_node.
    """

    # ------------------------------------------------------------------
    # Terminal state (all workflows)
    # ------------------------------------------------------------------

    final_response: Optional[Any]
    """
    The value placed into SentinelResponse.data at graph exit.

    For chat workflows: the validated response string.
    For document analysis: the DocumentSecurityDecision object.
    For knowledge upload: the IngestionResult object.
    For blocked requests: a structured dict describing the block reason.
    Populated by the terminal node of each workflow branch.
    """

    error: Optional[str]
    """
    Human-readable error message if a node raised an unexpected exception.
    When set, blocked is also set to True to terminate the workflow.
    Populated by any node on unrecoverable failure.
    """