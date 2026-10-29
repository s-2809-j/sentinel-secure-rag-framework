from __future__ import annotations
import logging
from src.knowledge_base.embedder import Embedder
from src.knowledge_base.vector_store import VectorStore
from src.knowledge_base.models import RetrievedChunk

logger = logging.getLogger(__name__)

class Retriever:

    DEFAULT_TOP_K = 5
    DEFAULT_THRESHOLD = 0.8

    def __init__(
            self,
            embedder: Embedder,
            vector_store: VectorStore,
            top_k: int | None = None,
            threshold: float | None = None) -> None:

        if embedder is None:
            raise ValueError("embedder cannot be none")
        
        if vector_store is None:
            raise ValueError("vector_store cannot be none")
              
        self.embedder = embedder
        self.vector_store = vector_store
        self.top_k = top_k or self.DEFAULT_TOP_K
        self.threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD

        logger.info(
            "Retriever initialized successfully (top_k=%d, threshold=%.2f)",
            self.top_k,
            self.threshold,
        )

    def retrieve(
            self,
            query: str,
            top_k: int | None = None,
            metadata_filter: dict[str, str] | None = None) -> list[RetrievedChunk]:

        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        k = top_k or self.top_k

        logger.info("Retrieving relevant chunks (top_k=%d, threshold=%.2f)", k, self.threshold)

        try:
            query_embedding = self.embedder.embed_query(query).tolist()
            results = self.vector_store.search(
                embedding=query_embedding,
                top_k=k,
                where=metadata_filter,
            )

            documents = results.get("documents") or []
            metadatas = results.get("metadatas") or []
            distances = results.get("distances") or []

            documents = documents[0] if documents else []
            metadatas = metadatas[0] if metadatas else []
            distances = distances[0] if distances else []

            raw_chunks: list[RetrievedChunk] = []

            for document, metadata, distance in zip(documents, metadatas, distances):
                # Clamp small negative floats from floating-point cosine math to 0.0
                clamped_dist = max(0.0, float(distance))
                raw_chunks.append(
                    RetrievedChunk(
                        content=document,
                        metadata=metadata,
                        distance=clamped_dist,
                    )
                )

            logger.debug(
                "Raw retrieval returned %d candidate chunks with distances: %s",
                len(raw_chunks),
                [round(c.distance, 4) for c in raw_chunks],
            )

            # Deduplicate by chunk_id (keep first occurrence)
            seen_ids: set[str] = set()
            deduped_chunks: list[RetrievedChunk] = []
            for chunk in raw_chunks:
                chunk_id = chunk.metadata.get("chunk_id", "")
                if chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    deduped_chunks.append(chunk)

            # Cosine distance in ChromaDB: 0 = identical, 2 = opposite.
            # 0.8 accepts chunks with cosine similarity >= 0.2 (relevant).
            retrieved_chunks = [
                c for c in deduped_chunks if c.distance <= self.threshold
            ]

            logger.info(
                "Successfully retrieved %d chunks (%d after dedup+threshold filtering at %.2f)",
                len(raw_chunks),
                len(retrieved_chunks),
                self.threshold,
            )

            return retrieved_chunks

        except Exception as exc:
            logger.error(
                "Failed to retrieve relevant chunks. %s: %s",
                type(exc).__name__,
                exc,
            )
            return []
