"""Test health endpoint."""


async def test_health_endpoint(client):
    """Test that health endpoint returns healthy status."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trading"
    assert "version" in data
