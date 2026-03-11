"""Mock embedding service for testing.

Provides a mock implementation of EmbeddingService that doesn't require
OpenAI API access, enabling fast, deterministic tests.
"""

from __future__ import annotations

from typing import Any


class MockEmbeddingService:
    """Mock OpenAI embedding service for testing.

    Generates deterministic embeddings without API calls.
    Tracks calls for verification in tests.
    """

    def __init__(
        self,
        dimension: int = 1536,
        default_value: float = 0.1,
    ) -> None:
        """Initialize the mock service.

        Args:
            dimension: Embedding dimension (default: 1536 for text-embedding-3-small)
            default_value: Default value for all embedding elements
        """
        self.dimension = dimension
        self.default_value = default_value
        self.calls: list[tuple[str, Any]] = []
        self._raise_on_generate: Exception | None = None
        self._custom_responses: dict[str, list[float]] = {}

    def reset(self) -> None:
        """Reset mock state."""
        self.calls = []
        self._raise_on_generate = None
        self._custom_responses = {}

    def set_error(self, error: Exception) -> None:
        """Configure the mock to raise an error on generate calls.

        Args:
            error: Exception to raise
        """
        self._raise_on_generate = error

    def set_response(self, text: str, embedding: list[float]) -> None:
        """Set a custom embedding response for a specific text.

        Args:
            text: Input text to match
            embedding: Embedding to return for this text
        """
        self._custom_responses[text] = embedding

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a mock embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Deterministic embedding vector

        Raises:
            ValueError: If text is empty
            RuntimeError: If mock is configured to raise errors
        """
        self.calls.append(("single", text))

        if self._raise_on_generate:
            raise self._raise_on_generate

        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Return custom response if configured
        if text in self._custom_responses:
            return self._custom_responses[text]

        # Generate deterministic embedding based on text hash
        # This ensures same text always produces same embedding
        return self._generate_deterministic_embedding(text)

    async def generate_embeddings_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Generate mock embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors in same order as input
        """
        self.calls.append(("batch", texts))

        if self._raise_on_generate:
            raise self._raise_on_generate

        if not texts:
            return []

        result: list[list[float]] = []
        for text in texts:
            if not text or not text.strip():
                result.append([])
            elif text in self._custom_responses:
                result.append(self._custom_responses[text])
            else:
                result.append(self._generate_deterministic_embedding(text))

        return result

    def _generate_deterministic_embedding(self, text: str) -> list[float]:
        """Generate a deterministic embedding based on text content.

        Uses a simple hash-based approach to generate consistent
        embeddings for the same input text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        # Create a simple hash-based embedding
        # This isn't semantically meaningful but is deterministic
        text_hash = hash(text)
        base_value = (text_hash % 1000) / 10000.0  # Small variation

        embedding = []
        for i in range(self.dimension):
            # Vary each dimension slightly based on position
            value = self.default_value + base_value + (i % 10) * 0.001
            # Normalize to reasonable embedding range
            value = max(-1.0, min(1.0, value))
            embedding.append(value)

        return embedding

    def get_call_count(self) -> int:
        """Get total number of generate calls.

        Returns:
            Number of calls made
        """
        return len(self.calls)

    def get_single_calls(self) -> list[str]:
        """Get list of texts from single generate calls.

        Returns:
            List of text strings
        """
        return [text for call_type, text in self.calls if call_type == "single"]

    def get_batch_calls(self) -> list[list[str]]:
        """Get list of text lists from batch generate calls.

        Returns:
            List of text lists
        """
        return [texts for call_type, texts in self.calls if call_type == "batch"]


class MockOpenAIClient:
    """Mock OpenAI client for testing EmbeddingService directly.

    Simulates the openai.AsyncOpenAI client interface.
    """

    def __init__(self, dimension: int = 1536) -> None:
        """Initialize the mock client.

        Args:
            dimension: Embedding dimension
        """
        self.dimension = dimension
        self.calls: list[dict[str, Any]] = []
        self._raise_on_create: Exception | None = None

    @property
    def embeddings(self) -> MockEmbeddingsEndpoint:
        """Get the embeddings endpoint."""
        return MockEmbeddingsEndpoint(self)

    def set_error(self, error: Exception) -> None:
        """Configure the mock to raise an error.

        Args:
            error: Exception to raise
        """
        self._raise_on_create = error


class MockEmbeddingsEndpoint:
    """Mock embeddings endpoint for OpenAI client."""

    def __init__(self, client: MockOpenAIClient) -> None:
        """Initialize the endpoint.

        Args:
            client: Parent mock client
        """
        self.client = client

    async def create(
        self,
        model: str,
        input: str | list[str],
    ) -> MockEmbeddingResponse:
        """Create embeddings (mock).

        Args:
            model: Model name
            input: Text or list of texts

        Returns:
            MockEmbeddingResponse
        """
        self.client.calls.append({"model": model, "input": input})

        if self.client._raise_on_create:
            raise self.client._raise_on_create

        # Handle single or batch input
        texts = [input] if isinstance(input, str) else input

        data = []
        for i, text in enumerate(texts):
            embedding = [0.1] * self.client.dimension
            data.append(MockEmbeddingObject(index=i, embedding=embedding))

        return MockEmbeddingResponse(data=data, model=model)


class MockEmbeddingObject:
    """Mock embedding object from OpenAI response."""

    def __init__(self, index: int, embedding: list[float]) -> None:
        """Initialize the embedding object.

        Args:
            index: Index in batch
            embedding: Embedding vector
        """
        self.index = index
        self.embedding = embedding


class MockEmbeddingResponse:
    """Mock embedding response from OpenAI API."""

    def __init__(
        self,
        data: list[MockEmbeddingObject],
        model: str,
    ) -> None:
        """Initialize the response.

        Args:
            data: List of embedding objects
            model: Model used
        """
        self.data = data
        self.model = model
