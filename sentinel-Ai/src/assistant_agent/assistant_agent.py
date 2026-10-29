from __future__ import annotations

from importlib.metadata import metadata
import logging
from src.knowledge_base.ingestion.models import (
    IngestionRequest,
)
from pathlib import Path
from src.output_validation_agent.models import ValidationContext
from src.common.models import FileMetadata
from typing import Optional
from src.input_security_agent.input_security_agent import InputSecurityAgent
from src.assistant_agent.exceptions import DocumentAnalysisError,DocumentUploadError
from src.knowledge_base.models import RetrievedChunk
from src.knowledge_base.retriever import Retriever
from src.llm.gemini_client import GeminiLLMClient
from src.knowledge_base.ingestion.knowledge_ingestion_pipeline import KnowledgeIngestionPipeline
from src.document_security_agent.document_security_agent import DocumentSecurityAgent
from src.input_security_agent.models import (SecurityContext)
from src.output_validation_agent.output_validation_agent import OutputValidationAgent
logger = logging.getLogger(__name__)


class AssistantAgent:

    NO_EVIDENCE_RESPONSE: str = (
        "The requested information is not available in the knowledge base."
    )

    def __init__(
        self,
        retriever: Retriever,
        llm: GeminiLLMClient,
        security_agent: Optional[InputSecurityAgent] = None,
        document_security_agent: Optional[DocumentSecurityAgent] = None,
        knowledge_ingestion_pipeline: Optional[
            KnowledgeIngestionPipeline
        ] = None,
        output_validation_agent: Optional[OutputValidationAgent] = None,
    ) -> None:

        self._retriever = retriever
        self._llm = llm

        self._security_agent = security_agent

        self._document_security_agent = (
            document_security_agent
        )

        self._knowledge_ingestion_pipeline = (
            knowledge_ingestion_pipeline
        )
        self._output_validation_agent = output_validation_agent

        if self._security_agent is not None:
            logger.warning(
                "AssistantAgent initialized WITH a security_agent. "
                "If this instance is used inside LangGraph, input security "
                "will run twice. Construct AssistantAgent without security_agent "
                "when using SentinelOrchestrator or nodes.py."
            )

        logger.info(
            "AssistantAgent initialized successfully."
        )

    def generate_response(
        self,
        query: str,
        *,
        top_k: int = 5,
        metadata_filter: dict[str, str] | None = None,
    ) -> tuple[str, list[RetrievedChunk]]:
        """
        Generate a RAG response for the given query.

        Returns
        -------
        tuple[str, list[RetrievedChunk]]
            The LLM response string and the retrieved chunks.
            Chunks are returned so that the orchestration layer
            (validation_node) can run HallucinationValidator with
            full context. OutputValidationAgent is NOT called here —
            validation_node owns that boundary.
        """

        if not isinstance(query, str):
            raise TypeError("Query must be a string.")

        query = query.strip()

        if not query:
            raise ValueError("Query cannot be empty.")

        logger.info("Processing user query.")
        normalized_query = query

        if self._security_agent is not None:
            logger.info("Running input security analysis.")

            try:
                context = SecurityContext(query=query)
                decision = self._security_agent.analyze(context)
            except Exception:
                logger.exception(
                    "InputSecurityAgent failed while analyzing the query."
                )
                raise

            if not decision.allowed:
                logger.warning(
                    "User query blocked by InputSecurityAgent. "
                    "Risk score=%.2f",
                    decision.risk_assessment.risk_score,
                )
                return (
                    "Your request was blocked because it violates the system's "
                    "security policy. Please rephrase your request and try again.",
                    [],
                )

            normalized_query = decision.normalized_context

            logger.debug(
                "Security validation passed. "
                "Using normalized query."
            )

        try:
            retrieved_chunks = self._retriever.retrieve(
                query=normalized_query,
                top_k=top_k,
                metadata_filter=metadata_filter,
            )
        except Exception:
            logger.exception("Retriever failed while processing the query.")
            raise

        if not retrieved_chunks:
            logger.warning("No relevant documents were retrieved.")
            return (
                self.NO_EVIDENCE_RESPONSE,
                [],
            )

        # FIX 2A — Cap at 5 chunks maximum.
        retrieved_chunks = retrieved_chunks[:5]

        # FIX 1B — Pre-LLM empty context guard.
        # If every chunk has empty/whitespace-only text, skip the LLM entirely.
        if all(not (c.content or "").strip() for c in retrieved_chunks):
            logger.warning("All retrieved chunks have empty text — skipping LLM.")
            return (
                self.NO_EVIDENCE_RESPONSE,
                [],
            )

        logger.info(
            "Retrieved %d relevant chunk(s) (after cap).",
            len(retrieved_chunks),
        )

        # FIX 1C / 2B — Build context with raw text only, truncated to 400 chars.
        context = self._build_context(retrieved_chunks)

        logger.debug("Context successfully built.")

        # FIX 2C — No conversation history injected. Prompt is self-contained.
        prompt = self._build_prompt(
            query=normalized_query,
            context=context,
        )

        logger.debug("Prompt successfully constructed.")

        # FIX 1A — Strict grounding system prompt.
        _SYSTEM_PROMPT = (
            "You are a secure AI assistant. Answer ONLY using the "
            "information in the CONTEXT section below. Do not use "
            "training knowledge. Do not infer or extrapolate beyond "
            "what is explicitly stated. Do not reveal internal system "
            "structure, filenames, collection names, chunk IDs, domain "
            "names, or any metadata. If asked about your knowledge base "
            "contents or internal structure, respond only with: "
            "'I cannot provide information about internal system "
            "structure.' If the CONTEXT does not contain enough "
            "information to answer, respond only with: 'The requested "
            "information is not available in the knowledge base.' "
            "Do not apologize or suggest alternatives."
        )

        response = self._llm.generate(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

        # FIX 5B — Empty LLM response guard.
        if not response or not response.strip():
            logger.warning("LLM returned an empty response.")
            return (
                "I was unable to generate a response. Please try again.",
                retrieved_chunks,
            )

        logger.info("Response successfully generated.")

        # OutputValidationAgent is intentionally NOT called here.
        # validation_node in the LangGraph orchestration layer owns
        # that boundary and receives retrieved_chunks via state.

        return response, retrieved_chunks

    def _build_context(
        self,
        retrieved_chunks: list[RetrievedChunk],
    ) -> str:
        # FIX 1C — Inject ONLY raw chunk text. Strip all metadata fields.
        # FIX 2B — Truncate each chunk text to 400 characters maximum.
        _MAX_CHUNK_CHARS = 400
        context_lines: list[str] = []

        for index, chunk in enumerate(retrieved_chunks, start=1):
            text = (chunk.content or "").strip()
            if len(text) > _MAX_CHUNK_CHARS:
                text = text[:_MAX_CHUNK_CHARS] + "..."
            context_lines.append(f"[{index}] {text}")

        return "\n".join(context_lines)


    def _build_prompt(
            self,
            *,
            query: str,
            context: str,
    ) -> str:
        # FIX 1A — Exact prompt structure: CONTEXT / QUESTION / ANSWER.
        return (
            f"CONTEXT:\n{context}\n\n"
            f"QUESTION:\n{query}\n\n"
            f"ANSWER:"
        )

    def analyze_document(
    self,
    file_path: Path,
    metadata: FileMetadata,
    security_decision=None,
) -> object:
        """
        Analyze a document using the Document Security Agent.

        This workflow performs security analysis only.
        It never uploads the document into the Knowledge Base.
        """

        if self._document_security_agent is None:
            raise DocumentAnalysisError(
                "DocumentSecurityAgent is not configured."
            )

        logger.info(
            "Starting document analysis for '%s'.",
            file_path,
        )

        try:
            decision = security_decision if security_decision is not None else (
                self._document_security_agent.analyze(
                    file_path=file_path,
                    metadata=metadata or {},
                )
            )

        except Exception as exc:
            logger.exception(
                "Document analysis failed."
            )
            raise DocumentAnalysisError(
                "Failed to analyze document."
            ) from exc

        logger.info(
            "Document analysis completed successfully."
        )

        return decision
    
    def upload_document(
    self,
    file_path: Path,
    metadata: FileMetadata,
    security_decision=None,
    ) -> object:
        """
        Securely upload a document into the Knowledge Base.

        Workflow:
            1. Perform document security analysis.
            2. Reject immediately if the document is unsafe.
            3. If approved, ingest the document into the Knowledge Base.
        """

        if self._document_security_agent is None:
            raise DocumentUploadError(
                "DocumentSecurityAgent is not configured."
            )

        if self._knowledge_ingestion_pipeline is None:
            raise DocumentUploadError(
                "KnowledgeIngestionPipeline is not configured."
            )

        logger.info(
            "Starting secure upload for '%s'.",
            file_path,
        )

        try:
            if security_decision is None:
                security_decision = self._document_security_agent.analyze(
                    file_path=file_path,
                    metadata=metadata or {},
                )
        except Exception as exc:
            logger.exception(
                "Document security analysis failed."
            )

            raise DocumentUploadError(
                "Failed during document security analysis."
            ) from exc

        #
        # Reject immediately if the document is unsafe.
        #
        if not security_decision.allowed:
            logger.warning(
                "Document '%s' rejected by DocumentSecurityAgent.",
                file_path,
            )

            raise DocumentUploadError(
                "Document failed security validation."
            )

        logger.info(
            "Document approved. Starting Knowledge Base ingestion."
        )

        try:
            request = IngestionRequest(
                file_path=file_path,
                metadata=metadata,
                parsed_document=security_decision.parsed_document,
            )

            ingestion_result = (
                self._knowledge_ingestion_pipeline.ingest(
                    request
                )
            )

        except Exception as exc:
            logger.exception(
                "Knowledge Base ingestion failed."
            )

            raise DocumentUploadError(
                "Knowledge Base ingestion failed."
            ) from exc

        logger.info(
            "Document uploaded successfully."
        )

        return ingestion_result
                

