"""
Data models for the Knowledge Ingestion Pipeline.

These models define the public contracts exchanged between the
Assistant Agent and the Knowledge Ingestion Pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from src.common.models import FileMetadata
from src.document_security_agent.models import ParsedDocument


class IngestionStatus(str, Enum):
    """Represents the final outcome of an ingestion operation."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(slots=True)
class IngestionRequest:
    """
    Request object for ingesting a validated document into the Knowledge Base.
    """

    file_path: Path
    metadata: FileMetadata
    parsed_document: ParsedDocument
    user_id: str | None = None


@dataclass(slots=True)
class IngestionResult:
    """
    Result returned after completion of the ingestion pipeline.
    """

    status: IngestionStatus
    success: bool
    document_id: str | None = None
    chunk_count: int = 0
    embedding_count: int = 0
    message: str = ""