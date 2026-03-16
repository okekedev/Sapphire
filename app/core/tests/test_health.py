"""
Tests for health check endpoint.
"""

import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_health_check_success(client):
    """GET /api/v1/health — returns 200 with service name."""
    response = await client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "service" in data
    assert data["service"] == "workforce"


@pytest.mark.asyncio
async def test_health_check_no_auth_required(client):
    """GET /api/v1/health — health check does not require authentication."""
    # Should work without any auth header
    response = await client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check_response_format(client):
    """GET /api/v1/health — response format is JSON."""
    response = await client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "status" in data
    assert "service" in data
