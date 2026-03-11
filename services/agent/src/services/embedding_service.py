"""Embedding service for generating vector embeddings.

This service handles embedding generation for semantic search using
OpenAI's text-embedding-3-small model.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Embedding model configuration
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Batch configuration
MAX_BATCH_SIZE = 100  # OpenAI's limit


class EmbeddingService:
    """Service for generating text embeddings using OpenAI.

    Uses text-embedding-3-small for cost efficiency ($0.02/1M tokens).
    Supports batched generation for efficiency.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        """Initialize the embedding service.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Embedding model to use
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Get or create the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("openai package not installed. Install with: pip install openai")

        return self._client

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (1536 dimensions for text-embedding-3-small)

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Truncate if too long (model limit is ~8k tokens)
        truncated_text = text[:32000] if len(text) > 32000 else text

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=truncated_text,
            )

            embedding = response.data[0].embedding

            logger.debug(
                "Generated embedding with %d dimensions for text of length %d",
                len(embedding),
                len(truncated_text),
            )

            return embedding

        except Exception as e:
            logger.exception("Failed to generate embedding: %s", e)
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    async def generate_embeddings_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts in batch.

        More efficient for multiple texts due to batched API calls.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors in same order as input

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not texts:
            return []

        # Filter empty texts and track indices
        non_empty: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            if text and text.strip():
                # Truncate if needed
                truncated = text[:32000] if len(text) > 32000 else text
                non_empty.append((i, truncated))

        if not non_empty:
            return [[] for _ in texts]

        # Process in batches
        all_embeddings: dict[int, list[float]] = {}

        for batch_start in range(0, len(non_empty), MAX_BATCH_SIZE):
            batch = non_empty[batch_start : batch_start + MAX_BATCH_SIZE]
            batch_texts = [t for _, t in batch]
            batch_indices = [i for i, _ in batch]

            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch_texts,
                )

                for idx, embedding_obj in zip(batch_indices, response.data):
                    all_embeddings[idx] = embedding_obj.embedding

            except Exception as e:
                logger.exception("Failed to generate batch embeddings: %s", e)
                raise RuntimeError(f"Batch embedding generation failed: {e}") from e

        # Build result in original order
        result: list[list[float]] = []
        for i in range(len(texts)):
            result.append(all_embeddings.get(i, []))

        logger.info(
            "Generated %d embeddings in %d batches",
            len(all_embeddings),
            (len(non_empty) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE,
        )

        return result


# Global instance for reuse
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
