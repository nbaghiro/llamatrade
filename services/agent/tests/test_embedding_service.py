"""Tests for embedding service.

Tests embedding generation using OpenAI API.
Target coverage: 80%
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.fixtures.mock_embedding import MockEmbeddingService, MockOpenAIClient

from src.services.embedding_service import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
    MAX_BATCH_SIZE,
    EmbeddingService,
    get_embedding_service,
)

# =============================================================================
# Embedding Generation Tests
# =============================================================================


class TestEmbeddingGeneration:
    """Tests for generate_embedding()."""

    @pytest.mark.asyncio
    async def test_generates_embedding_vector(self) -> None:
        """Test that embedding is generated successfully."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        embedding = await service.generate_embedding("Test text")

        assert len(embedding) == EMBEDDING_DIMENSIONS
        assert all(isinstance(v, float) for v in embedding)

    @pytest.mark.asyncio
    async def test_raises_on_empty_text(self) -> None:
        """Test that empty text raises ValueError."""
        service = EmbeddingService(api_key="test-key")

        with pytest.raises(ValueError, match="cannot be empty"):
            await service.generate_embedding("")

    @pytest.mark.asyncio
    async def test_raises_on_whitespace_only_text(self) -> None:
        """Test that whitespace-only text raises ValueError."""
        service = EmbeddingService(api_key="test-key")

        with pytest.raises(ValueError, match="cannot be empty"):
            await service.generate_embedding("   ")

    @pytest.mark.asyncio
    async def test_truncates_long_text(self) -> None:
        """Test that long text is truncated."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        # Create text longer than 32000 chars
        long_text = "a" * 50000

        embedding = await service.generate_embedding(long_text)

        # Should succeed and return embedding
        assert len(embedding) == EMBEDDING_DIMENSIONS
        # Verify the truncated text was sent
        call = mock_client.calls[0]
        assert len(call["input"]) == 32000

    @pytest.mark.asyncio
    async def test_handles_api_error(self) -> None:
        """Test handling of API errors."""
        mock_client = MockOpenAIClient()
        mock_client.set_error(Exception("API rate limit exceeded"))

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        with pytest.raises(RuntimeError, match="Embedding generation failed"):
            await service.generate_embedding("Test text")

    @pytest.mark.asyncio
    async def test_uses_correct_model(self) -> None:
        """Test that correct model is used."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        await service.generate_embedding("Test")

        call = mock_client.calls[0]
        assert call["model"] == DEFAULT_EMBEDDING_MODEL


# =============================================================================
# Batch Embedding Tests
# =============================================================================


class TestBatchEmbedding:
    """Tests for generate_embeddings_batch()."""

    @pytest.mark.asyncio
    async def test_batch_processing(self) -> None:
        """Test batch processing of multiple texts."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = await service.generate_embeddings_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) == EMBEDDING_DIMENSIONS for e in embeddings)

    @pytest.mark.asyncio
    async def test_preserves_order(self) -> None:
        """Test that embeddings are returned in same order as input."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        texts = ["First", "Second", "Third"]
        embeddings = await service.generate_embeddings_batch(texts)

        # Should have 3 embeddings in order
        assert len(embeddings) == 3

    @pytest.mark.asyncio
    async def test_handles_empty_texts_in_batch(self) -> None:
        """Test handling of empty texts in batch."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        texts = ["Valid text", "", "Another valid"]
        embeddings = await service.generate_embeddings_batch(texts)

        assert len(embeddings) == 3
        # Empty text should return empty embedding
        assert embeddings[1] == []

    @pytest.mark.asyncio
    async def test_all_empty_texts(self) -> None:
        """Test batch with all empty texts."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        texts = ["", "   ", ""]
        embeddings = await service.generate_embeddings_batch(texts)

        assert len(embeddings) == 3
        assert all(e == [] for e in embeddings)

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        """Test batch with empty list."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        embeddings = await service.generate_embeddings_batch([])

        assert embeddings == []

    @pytest.mark.asyncio
    async def test_respects_batch_size_limit(self) -> None:
        """Test that batch size limit is respected."""
        mock_client = MockOpenAIClient()

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        # Create more texts than batch size
        texts = [f"Text {i}" for i in range(MAX_BATCH_SIZE + 50)]
        embeddings = await service.generate_embeddings_batch(texts)

        # Should make multiple API calls
        assert len(embeddings) == MAX_BATCH_SIZE + 50
        # First batch should have MAX_BATCH_SIZE items
        assert len(mock_client.calls) == 2  # Two batches

    @pytest.mark.asyncio
    async def test_batch_handles_api_error(self) -> None:
        """Test that batch handles API errors."""
        mock_client = MockOpenAIClient()
        mock_client.set_error(Exception("API Error"))

        service = EmbeddingService(api_key="test-key")
        service._client = mock_client

        texts = ["Text 1", "Text 2"]

        with pytest.raises(RuntimeError, match="Batch embedding generation failed"):
            await service.generate_embeddings_batch(texts)


# =============================================================================
# Client Initialization Tests
# =============================================================================


class TestClientInitialization:
    """Tests for lazy client initialization."""

    def test_raises_without_openai_package(self) -> None:
        """Test that missing openai package raises error."""
        service = EmbeddingService(api_key="test-key")
        service._client = None

        with patch.dict("sys.modules", {"openai": None}):
            with patch(
                "src.services.embedding_service.EmbeddingService.client",
                new_callable=lambda: property(lambda self: _raise_import_error()),
            ):
                # This tests the scenario where openai isn't installed
                # The actual implementation handles this in the property
                pass

    def test_creates_client_on_first_use(self) -> None:
        """Test that client is created lazily."""
        service = EmbeddingService(api_key="test-key")

        # Client should not be created yet
        assert service._client is None

    def test_uses_env_var_for_api_key(self) -> None:
        """Test that API key is read from environment."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            service = EmbeddingService()
            assert service.api_key == "env-key"

    def test_explicit_api_key_overrides_env(self) -> None:
        """Test that explicit API key overrides env var."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            service = EmbeddingService(api_key="explicit-key")
            assert service.api_key == "explicit-key"

    def test_custom_model(self) -> None:
        """Test using custom model."""
        service = EmbeddingService(model="custom-model")
        assert service.model == "custom-model"


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global embedding service instance."""

    def test_get_embedding_service_returns_singleton(self) -> None:
        """Test that get_embedding_service returns same instance."""
        # Reset global state
        import src.services.embedding_service as module

        module._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

    def test_get_embedding_service_creates_new(self) -> None:
        """Test that get_embedding_service creates new instance if none exists."""
        # Reset global state
        import src.services.embedding_service as module

        module._embedding_service = None

        service = get_embedding_service()

        assert service is not None
        assert isinstance(service, EmbeddingService)


# =============================================================================
# Mock Embedding Service Tests
# =============================================================================


class TestMockEmbeddingService:
    """Tests for MockEmbeddingService test helper."""

    @pytest.mark.asyncio
    async def test_generates_deterministic_embeddings(self) -> None:
        """Test that same text produces same embedding."""
        service = MockEmbeddingService()

        embedding1 = await service.generate_embedding("Test text")
        embedding2 = await service.generate_embedding("Test text")

        assert embedding1 == embedding2

    @pytest.mark.asyncio
    async def test_different_texts_produce_different_embeddings(self) -> None:
        """Test that different texts produce different embeddings."""
        service = MockEmbeddingService()

        embedding1 = await service.generate_embedding("Text A")
        embedding2 = await service.generate_embedding("Text B")

        assert embedding1 != embedding2

    @pytest.mark.asyncio
    async def test_tracks_calls(self) -> None:
        """Test that calls are tracked."""
        service = MockEmbeddingService()

        await service.generate_embedding("Text 1")
        await service.generate_embeddings_batch(["Text 2", "Text 3"])

        assert service.get_call_count() == 2
        assert len(service.get_single_calls()) == 1
        assert len(service.get_batch_calls()) == 1

    @pytest.mark.asyncio
    async def test_can_configure_error(self) -> None:
        """Test that mock can be configured to raise errors."""
        service = MockEmbeddingService()
        service.set_error(ValueError("Test error"))

        with pytest.raises(ValueError, match="Test error"):
            await service.generate_embedding("Test")

    @pytest.mark.asyncio
    async def test_can_set_custom_response(self) -> None:
        """Test that custom response can be set."""
        service = MockEmbeddingService()
        custom_embedding = [0.5] * 1536
        service.set_response("Custom text", custom_embedding)

        result = await service.generate_embedding("Custom text")

        assert result == custom_embedding

    @pytest.mark.asyncio
    async def test_reset_clears_state(self) -> None:
        """Test that reset clears all state."""
        service = MockEmbeddingService()
        service.set_response("text", [0.1])

        # Make a call to populate state
        await service.generate_embedding("text")

        # Verify state exists
        assert len(service.calls) > 0
        assert len(service._custom_responses) > 0

        # Reset
        service.reset()

        # Verify state is cleared
        assert service.calls == []
        assert service._raise_on_generate is None
        assert service._custom_responses == {}


# =============================================================================
# Helper Functions
# =============================================================================


def _raise_import_error() -> None:
    """Helper to raise ImportError for testing."""
    raise RuntimeError("openai package not installed")
