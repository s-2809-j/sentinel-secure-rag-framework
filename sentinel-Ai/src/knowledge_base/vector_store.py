from __future__ import annotations

import logging
from pathlib import Path
import chromadb
from src.knowledge_base.embedder import EmbeddedChunk

logger = logging.getLogger(__name__)

class VectorStore:

    DEFAULT_COLLECTION = "sentinel_knowledge_base"

    def __init__(self, db_path: str | Path = "chroma_db", collection_name: str | None = None) -> None:
        
        self.db_path = Path(db_path)

        self._collection_name = (
            collection_name or self.DEFAULT_COLLECTION
        )

        logger.info(
            "Initializing ChromaDB at %s",
            self.db_path,
        )

        try:
            self.client = chromadb.PersistentClient(
                path=str(self.db_path)
            )

            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            # If collection pre-existed without cosine metric, migrate to cosine space
            if (
                self._collection.metadata is None
                or self._collection.metadata.get("hnsw:space") != "cosine"
            ):
                logger.warning(
                    "Collection '%s' is not using cosine distance. Migrating to cosine space.",
                    self.collection_name,
                )
                existing = self._collection.get(
                    include=["embeddings", "documents", "metadatas"]
                )
                self.client.delete_collection(name=self.collection_name)
                self._collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                if existing.get("ids"):
                    self._collection.add(
                        ids=existing["ids"],
                        documents=existing.get("documents"),
                        metadatas=existing.get("metadatas"),
                        embeddings=existing.get("embeddings"),
                    )
                logger.info(
                    "Successfully migrated collection '%s' to cosine distance space.",
                    self.collection_name,
                )

            logger.info(
                "Connected to collection %s (metric: cosine)",
                self._collection_name,
            )

        except Exception as exc:
            logger.exception(
                "Failed to initialize ChromaDB."
            )
            raise RuntimeError(
                "unable to initialize the vector store."
            ) from exc

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def store(
            self,
            embedded_chunks: list[EmbeddedChunk]
    ) -> None:
        
        if not embedded_chunks:
            logger.warning("No embedded chunks provided for collection '%s'.", self.collection_name)
            return
    
        logger.info("Storing %d embedded chunks into collection %s", len(embedded_chunks), self.collection_name)

        try:
            ids = [
                chunk.metadata["chunk_id"]
                for chunk in embedded_chunks
            ]    
            documents = [
                chunk.content
                for chunk in embedded_chunks
            ]
            embeddings = [
                chunk.embedding.tolist() if hasattr(chunk.embedding, 'tolist') else chunk.embedding
                for chunk in embedded_chunks
            ]

            metadatas = [
                chunk.metadata
                for chunk in embedded_chunks
            ]

            self._collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings, 
                metadatas=metadatas
            )

            logger.info(
                "Successfully stored %d embedded chunks",
                len(embedded_chunks)
            )

        except Exception as exc:
            logger.exception(
                "Failed to store embedded chunks"
            )

            raise RuntimeError(
                "Failed to store embedded chunks"
            ) from exc
        
    def search(
            self,
            embedding: list[float],
            top_k: int = 5,
            where: dict | None = None,
    ) -> dict:
        
        logger.info(
            "searching collection %s (top_k = %d)",
            self.collection_name,
            top_k,
        )

        try:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where,
            )

            logger.info(
                "Search completed successfully"
            )

            return results
        
        except Exception as exc:
            logger.exception("Vector search failed")
            raise RuntimeError("Failed to search the vector store") from exc

    def count(self) -> int:
        return self._collection.count()

    def exists_by_checksum(
        self, checksum: str, user_id: str | None = None
    ) -> bool:
        """
        FIX 4B — Duplicate document prevention.

        Query the collection for any document whose metadata checksum
        matches the provided value (optionally scoped to user_id).
        Returns True if the document has already been ingested.
        """
        try:
            if user_id:
                where: dict = {
                    "$and": [
                        {"checksum": checksum},
                        {"user_id": user_id},
                    ]
                }
            else:
                where = {"checksum": checksum}
            result = self._collection.get(where=where)
            return bool(result.get("ids"))
        except Exception as exc:
            logger.error(
                "exists_by_checksum query failed for checksum=%s user_id=%s. %s: %s",
                checksum,
                user_id,
                type(exc).__name__,
                exc,
            )
            return False

    def clear(self) -> None:
        try:
            ids = self._collection.get()["ids"]

            if ids:
                self._collection.delete(ids=ids)

            logger.info(
                "Collection '%s' cleared.",
                self._collection_name,
            )

        except Exception as exc:
            logger.exception(
                "Failed to clear collection."
            )
            raise RuntimeError(
                "Failed to clear the collection."
            ) from exc
