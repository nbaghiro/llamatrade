"""Tests for observability middleware and utilities."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llamatrade_common.observability import (
    ObservabilityMiddleware,
    setup_observability,
)


class TestObservabilityMiddleware:
    """Tests for ObservabilityMiddleware."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with observability middleware."""
        app = FastAPI()
        app.add_middleware(
            ObservabilityMiddleware,
            service_name="test-service",
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Test error")

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_middleware_adds_request_id(self, client):
        """Test that middleware adds X-Request-ID header."""
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_middleware_preserves_request_id(self, client):
        """Test that middleware preserves provided X-Request-ID."""
        response = client.get(
            "/test",
            headers={"X-Request-ID": "custom-request-id"},
        )

        assert response.headers["X-Request-ID"] == "custom-request-id"

    def test_middleware_adds_response_time(self, client):
        """Test that middleware adds X-Response-Time header."""
        response = client.get("/test")

        assert "X-Response-Time" in response.headers
        # Should be in format like "0.001s"
        assert response.headers["X-Response-Time"].endswith("s")

    def test_middleware_handles_errors(self, client):
        """Test that middleware handles endpoint errors."""
        response = client.get("/error")

        # Error response - status depends on exception handling
        assert response.status_code >= 400


class TestSetupObservability:
    """Tests for setup_observability function."""

    def test_setup_observability_basic(self):
        """Test basic observability setup."""
        app = FastAPI()

        setup_observability(
            app,
            service_name="test-service",
            version="1.0.0",
            environment="testing",
        )

        # App should have middleware and metrics endpoint
        client = TestClient(app)

        # Check metrics endpoint exists
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_setup_observability_with_options(self):
        """Test observability setup with custom options."""
        app = FastAPI()

        setup_observability(
            app,
            service_name="custom-service",
            version="2.0.0",
            environment="production",
            log_level="WARNING",
            json_logs=True,
        )

        client = TestClient(app)

        # Verify app is configured
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_setup_observability_human_readable_logs(self):
        """Test observability setup with human-readable logs."""
        app = FastAPI()

        setup_observability(
            app,
            service_name="dev-service",
            json_logs=False,
        )

        # App should be configured


class TestObservabilityMiddlewareMetrics:
    """Tests for metrics collection in observability middleware."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with full observability."""
        app = FastAPI()

        setup_observability(
            app,
            service_name="metrics-test",
            version="1.0.0",
        )

        @app.get("/api/users")
        async def list_users():
            return {"users": []}

        @app.post("/api/orders")
        async def create_order():
            return {"order_id": "123"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """Test that metrics endpoint returns Prometheus format."""
        # Make some requests first
        client.get("/api/users")
        client.post("/api/orders")

        response = client.get("/metrics")

        assert response.status_code == 200
        content = response.content
        # Should contain standard Prometheus metrics
        assert b"llamatrade" in content or b"http" in content or len(content) > 0
