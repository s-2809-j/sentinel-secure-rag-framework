"""
Knowledge Ingestion Pipeline.
"""

from __future__ import annotations

import logging

from src.knowledge_base.chunker import TextChunker
from src.knowledge_base.embedder import Embedder
from src.knowledge_base.models import Document
from src.knowledge_base.vector_store import VectorStore

from .exceptions import KnowledgeIngestionError
from .models import (
    IngestionRequest,
    IngestionResult,
    IngestionStatus,
)

logger = logging.getLogger(__name__)


class KnowledgeIngestionPipeline:
    """
    Pipeline responsible for ingesting a validated document
    into the Knowledge Base.

    The document is expected to have already passed all
    security validation and parsing inside the
    Document Security Pipeline.

    This pipeline no longer loads or parses files from disk.
    It consumes a ParsedDocument produced by the
    Document Security Pipeline.
    """

    def __init__(
        self,
        *,
        chunker: TextChunker,
        embedder: Embedder,
        vector_store: VectorStore,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    def ingest(
        self,
        request: IngestionRequest,
    ) -> IngestionResult:
        """
        Ingest a validated ParsedDocument into the Knowledge Base.
        """

        logger.info(
            "Starting knowledge ingestion for %s",
            request.file_path,
        )

        try:
            parsed = request.parsed_document

            # FIX 4A — Empty document guard.
            if not parsed.text or not parsed.text.strip():
                raise ValueError(
                    "Document contains no extractable text. "
                    "Scanned image PDFs are not supported."
                )

            # FIX 6C — Prompt injection content scan.
            _INJECTION_PATTERNS = [
                "ignore previous instructions",
                "disregard your instructions",
                "you are now",
                "new instruction:",
                "system prompt:",
                "forget everything",
            ]
            lowered_text = parsed.text.lower()
            for pattern in _INJECTION_PATTERNS:
                if pattern in lowered_text:
                    raise ValueError(
                        "Document contains prompt injection content and cannot "
                        "be ingested."
                    )

            # FIX 4B — Duplicate document prevention via checksum (scoped by user).
            checksum = parsed.metadata.checksum
            if checksum and self._vector_store.exists_by_checksum(
                checksum, user_id=request.user_id
            ):
                logger.info(
                    "Document with checksum %s already ingested for user_id=%s — skipping.",
                    checksum,
                    request.user_id,
                )
                return IngestionResult(
                    status=IngestionStatus.SUCCESS,
                    success=True,
                    chunk_count=0,
                    embedding_count=0,
                    message="Document already ingested.",
                )

            chunk_metadata = {
                "domain": "uploaded",
                "document_name": parsed.metadata.filename,
                "source": parsed.metadata.filename,
                "section": "root",
                "malicious": False,
                "filename": parsed.metadata.filename,
                "extension": parsed.metadata.extension,
                "mime_type": parsed.metadata.mime_type,
                "size_bytes": parsed.metadata.size_bytes,
                "checksum": parsed.metadata.checksum,
                "parser": parsed.parser_name,
                "page_count": parsed.page_count,
            }
            if request.user_id:
                chunk_metadata["user_id"] = request.user_id

            document = Document(
                content=parsed.text,
                metadata=chunk_metadata,
            )

            #
            # Step 2 - Chunk
            #
            chunks = self._chunker.chunk_documents([document])

            #
            # Step 3 - Embed
            #
            embedded_chunks = self._embedder.embed(chunks)

            #
            # Step 4 - Store
            #
            self._vector_store.store(embedded_chunks)

            logger.info("Knowledge ingestion completed successfully.")

            return IngestionResult(
                status=IngestionStatus.SUCCESS,
                success=True,
                chunk_count=len(chunks),
                embedding_count=len(embedded_chunks),
                message="Document successfully ingested.",
            )

        except Exception as exc:
            logger.exception("Knowledge ingestion failed.")

            raise KnowledgeIngestionError(str(exc)) from exc
