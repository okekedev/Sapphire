"""
Tests for platform connection routes — OAuth flow and API key management.
"""

import pytest
from uuid import UUID

from app.config import settings


# ── API Key Connections ──


@pytest.mark.asyncio
async def test_connect_api_key_success(client, auth_helper, business_helper):
    """POST /api/v1/platforms/connect/api-key — connect API key platform."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            "api_key": "test-api-key-12345",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    account = data["data"]
    assert account["platform"] == "ahrefs"
    assert "connected_at" in account


@pytest.mark.asyncio
async def test_connect_api_key_requires_auth(client, business_helper, auth_helper):
    """POST /api/v1/platforms/connect/api-key — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            "api_key": "test-api-key",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_connect_api_key_invalid_platform(client, auth_helper, business_helper):
    """POST /api/v1/platforms/connect/api-key — invalid platform returns 400."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "invalid-platform",
            "api_key": "test-api-key",
        },
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_connect_api_key_missing_field(client, auth_helper, business_helper):
    """POST /api/v1/platforms/connect/api-key — missing required field returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            # Missing api_key
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_connect_api_key_with_department_id(client, auth_helper, business_helper, department_helper):
    """POST /api/v1/platforms/connect/api-key — connect with department scope."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "department_id": str(dept_id),
            "platform": "semrush",
            "api_key": "dept-api-key-xyz",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    account = data["data"]
    assert account["department_id"] == str(dept_id)


# ── List Connections ──


@pytest.mark.asyncio
async def test_list_connections_empty(client, auth_helper, business_helper):
    """GET /api/v1/platforms/connections — list with no connections returns empty list."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/platforms/connections?business_id={business_id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 0


@pytest.mark.asyncio
async def test_list_connections_success(client, auth_helper, business_helper):
    """GET /api/v1/platforms/connections — list connections."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # Create a connection
    await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            "api_key": "test-key",
        },
        headers=headers,
    )

    # List connections
    response = await client.get(
        f"{settings.api_prefix}/platforms/connections?business_id={business_id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    connections = data["data"]
    assert len(connections) == 1
    assert connections[0]["platform"] == "ahrefs"


@pytest.mark.asyncio
async def test_list_connections_requires_auth(client, business_helper, auth_helper):
    """GET /api/v1/platforms/connections — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/platforms/connections?business_id={business_id}",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_connections_missing_business_id(client, auth_helper):
    """GET /api/v1/platforms/connections — missing business_id returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.get(
        f"{settings.api_prefix}/platforms/connections",
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_connections_filter_by_department(client, auth_helper, business_helper, department_helper):
    """GET /api/v1/platforms/connections — filter by department_id."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    # Create business-wide connection
    await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            "api_key": "business-key",
        },
        headers=headers,
    )

    # Create department-scoped connection
    await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "department_id": str(dept_id),
            "platform": "semrush",
            "api_key": "dept-key",
        },
        headers=headers,
    )

    # List all connections
    all_response = await client.get(
        f"{settings.api_prefix}/platforms/connections?business_id={business_id}",
        headers=headers,
    )
    all_data = all_response.json()
    assert len(all_data["data"]) == 2

    # List only department connections
    dept_response = await client.get(
        f"{settings.api_prefix}/platforms/connections?business_id={business_id}&department_id={dept_id}",
        headers=headers,
    )
    dept_data = dept_response.json()
    assert len(dept_data["data"]) == 1
    assert dept_data["data"][0]["platform"] == "semrush"


# ── Disconnect ──


@pytest.mark.asyncio
async def test_disconnect_platform_success(client, auth_helper, business_helper):
    """POST /api/v1/platforms/disconnect — disconnect platform."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # Create connection first
    await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            "api_key": "test-key",
        },
        headers=headers,
    )

    # Disconnect
    response = await client.post(
        f"{settings.api_prefix}/platforms/disconnect",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "disconnected"

    # Verify connection is marked as revoked
    list_response = await client.get(
        f"{settings.api_prefix}/platforms/connections?business_id={business_id}",
        headers=headers,
    )
    list_data = list_response.json()
    assert len(list_data["data"]) == 1
    assert list_data["data"][0]["status"] == "revoked"


@pytest.mark.asyncio
async def test_disconnect_nonexistent_connection(client, auth_helper, business_helper):
    """POST /api/v1/platforms/disconnect — nonexistent connection returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/disconnect",
        json={
            "business_id": str(business_id),
            "platform": "nonexistent-platform",
        },
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_disconnect_requires_auth(client, business_helper, auth_helper):
    """POST /api/v1/platforms/disconnect — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/disconnect",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_disconnect_missing_field(client, auth_helper, business_helper):
    """POST /api/v1/platforms/disconnect — missing required field returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/disconnect",
        json={
            "business_id": str(business_id),
            # Missing platform
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_disconnect_department_scoped(client, auth_helper, business_helper, department_helper):
    """POST /api/v1/platforms/disconnect — disconnect department-scoped connection."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    # Create department-scoped connection
    await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "department_id": str(dept_id),
            "platform": "semrush",
            "api_key": "dept-key",
        },
        headers=headers,
    )

    # Disconnect department-scoped connection
    response = await client.post(
        f"{settings.api_prefix}/platforms/disconnect",
        json={
            "business_id": str(business_id),
            "department_id": str(dept_id),
            "platform": "semrush",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


# ── Test Connection ──


@pytest.mark.asyncio
async def test_test_connection_success(client, auth_helper, business_helper):
    """GET /api/v1/platforms/test/{platform} — test platform connection when no connection exists."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # Try to test a connection that doesn't exist
    response = await client.get(
        f"{settings.api_prefix}/platforms/test/ahrefs?business_id={business_id}",
        headers=headers,
    )
    # Should return 404 because no connection exists
    assert response.status_code == 404



@pytest.mark.asyncio
async def test_test_connection_not_found(client, auth_helper, business_helper):
    """GET /api/v1/platforms/test/{platform} — no connection returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/platforms/test/ahrefs?business_id={business_id}",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_connection_requires_auth(client, business_helper, auth_helper):
    """GET /api/v1/platforms/test/{platform} — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/platforms/test/ahrefs?business_id={business_id}",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_test_connection_missing_business_id(client, auth_helper):
    """GET /api/v1/platforms/test/{platform} — missing business_id returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.get(
        f"{settings.api_prefix}/platforms/test/ahrefs",
        headers=headers,
    )
    assert response.status_code == 422


# ── Refresh Token ──


@pytest.mark.asyncio
async def test_refresh_platform_token_success(client, auth_helper, business_helper):
    """POST /api/v1/platforms/refresh — refresh platform token not supported for API key platforms."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # Create connection
    await client.post(
        f"{settings.api_prefix}/platforms/connect/api-key",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
            "api_key": "test-key",
        },
        headers=headers,
    )

    # Refresh token returns 400 for API key platforms (they don't have tokens to refresh)
    response = await client.post(
        f"{settings.api_prefix}/platforms/refresh",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
        },
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refresh_platform_token_not_found(client, auth_helper, business_helper):
    """POST /api/v1/platforms/refresh — nonexistent connection returns 400."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/refresh",
        json={
            "business_id": str(business_id),
            "platform": "nonexistent",
        },
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refresh_platform_token_requires_auth(client, business_helper, auth_helper):
    """POST /api/v1/platforms/refresh — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/platforms/refresh",
        json={
            "business_id": str(business_id),
            "platform": "ahrefs",
        },
    )
    assert response.status_code == 401
