"""
Tests for authentication routes — registration, login, token refresh.
"""

import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_register_success(client):
    """POST /api/v1/auth/register — successful registration returns tokens."""
    response = await client.post(
        f"{settings.api_prefix}/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePassword123!",
            "full_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client, auth_helper):
    """POST /api/v1/auth/register — duplicate email returns 409."""
    # First registration
    await auth_helper(email="duplicate@example.com")

    # Second registration with same email
    response = await client.post(
        f"{settings.api_prefix}/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "AnotherPassword123!",
            "full_name": "Another User",
        },
    )
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_invalid_email(client):
    """POST /api/v1/auth/register — invalid email format returns 422."""
    response = await client.post(
        f"{settings.api_prefix}/auth/register",
        json={
            "email": "not-an-email",
            "password": "SecurePassword123!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_field(client):
    """POST /api/v1/auth/register — missing required field returns 422."""
    response = await client.post(
        f"{settings.api_prefix}/auth/register",
        json={
            "email": "test@example.com",
            "password": "SecurePassword123!",
            # Missing full_name
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_password(client):
    """POST /api/v1/auth/register — missing password field returns 422."""
    response = await client.post(
        f"{settings.api_prefix}/auth/register",
        json={
            "email": "test@example.com",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client, auth_helper):
    """POST /api/v1/auth/login — successful login returns tokens."""
    email = "login@example.com"
    password = "LoginPassword123!"

    # Register user first
    await auth_helper(email=email, password=password)

    # Login
    response = await client.post(
        f"{settings.api_prefix}/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, auth_helper):
    """POST /api/v1/auth/login — wrong password returns 401."""
    email = "wrongpass@example.com"
    await auth_helper(email=email, password="CorrectPassword123!")

    response = await client.post(
        f"{settings.api_prefix}/auth/login",
        json={
            "email": email,
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_email(client):
    """POST /api/v1/auth/login — nonexistent email returns 401."""
    response = await client.post(
        f"{settings.api_prefix}/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "AnyPassword123!",
        },
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_invalid_email_format(client):
    """POST /api/v1/auth/login — invalid email format returns 422."""
    response = await client.post(
        f"{settings.api_prefix}/auth/login",
        json={
            "email": "not-an-email",
            "password": "AnyPassword123!",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_missing_field(client):
    """POST /api/v1/auth/login — missing required field returns 422."""
    response = await client.post(
        f"{settings.api_prefix}/auth/login",
        json={
            "email": "test@example.com",
            # Missing password
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_refresh_token_success(client, auth_helper):
    """POST /api/v1/auth/refresh — valid refresh token returns new tokens."""
    auth_info = await auth_helper()
    refresh_token = auth_info["refresh_token"]

    response = await client.post(
        f"{settings.api_prefix}/auth/refresh",
        params={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_invalid_token(client):
    """POST /api/v1/auth/refresh — invalid token returns 401."""
    response = await client.post(
        f"{settings.api_prefix}/auth/refresh",
        params={"refresh_token": "invalid.token.here"},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_with_access_token(client, auth_helper):
    """POST /api/v1/auth/refresh — using access token instead of refresh returns 401."""
    auth_info = await auth_helper()
    access_token = auth_info["access_token"]

    response = await client.post(
        f"{settings.api_prefix}/auth/refresh",
        params={"refresh_token": access_token},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_refresh_malformed_token(client):
    """POST /api/v1/auth/refresh — malformed token returns 401."""
    response = await client.post(
        f"{settings.api_prefix}/auth/refresh",
        params={"refresh_token": "not.a.token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_missing_token(client):
    """POST /api/v1/auth/refresh — missing token field returns 422."""
    response = await client.post(
        f"{settings.api_prefix}/auth/refresh",
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_token_can_be_used(client):
    """POST /api/v1/auth/register — returned access token is valid."""
    response = await client.post(
        f"{settings.api_prefix}/auth/register",
        json={
            "email": "tokentest@example.com",
            "password": "SecurePassword123!",
            "full_name": "Token Test User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    access_token = data["access_token"]

    # Use the token to access a protected endpoint
    headers = {"Authorization": f"Bearer {access_token}"}
    list_response = await client.get(
        f"{settings.api_prefix}/businesses",
        headers=headers,
    )
    # Should succeed (200) or at least not 401/403
    assert list_response.status_code in [200, 204]
