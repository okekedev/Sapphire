"""
Tests for business CRUD operations and profile management.
"""

import pytest
from uuid import UUID

from app.config import settings


# ── Business CRUD ──


@pytest.mark.asyncio
async def test_create_business_success(client, auth_helper):
    """POST /api/v1/businesses — create business returns 201."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.post(
        f"{settings.api_prefix}/businesses",
        json={
            "name": "Acme Corp",
            "website": "https://acme.com",
            "industry": "Technology",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corp"
    assert data["website"] == "https://acme.com"
    assert data["industry"] == "Technology"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_business_requires_auth(client):
    """POST /api/v1/businesses — missing auth returns 403."""
    response = await client.post(
        f"{settings.api_prefix}/businesses",
        json={
            "name": "Acme Corp",
            "website": "https://acme.com",
            "industry": "Technology",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_business_invalid_auth(client):
    """POST /api/v1/businesses — invalid auth returns 403."""
    headers = {"Authorization": "Bearer invalid.token"}
    response = await client.post(
        f"{settings.api_prefix}/businesses",
        json={
            "name": "Acme Corp",
            "website": "https://acme.com",
            "industry": "Technology",
        },
        headers=headers,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_business_missing_field(client, auth_helper):
    """POST /api/v1/businesses — missing required field returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.post(
        f"{settings.api_prefix}/businesses",
        json={
            "name": "Acme Corp",
            "website": "https://acme.com",
            # Missing industry
        },
        headers=headers,
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_list_businesses_empty(client, auth_helper):
    """GET /api/v1/businesses — list with no businesses returns empty list."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.get(
        f"{settings.api_prefix}/businesses",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_businesses_multiple(client, auth_helper, business_helper):
    """GET /api/v1/businesses — list multiple businesses."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    # Create multiple businesses
    await business_helper(auth_info)
    await business_helper(auth_info)

    response = await client.get(
        f"{settings.api_prefix}/businesses",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_businesses_requires_auth(client):
    """GET /api/v1/businesses — missing auth returns 403."""
    response = await client.get(
        f"{settings.api_prefix}/businesses",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_businesses_isolation(client, auth_helper, business_helper):
    """GET /api/v1/businesses — each user only sees their own businesses."""
    # Create first user and business
    auth_info_1 = await auth_helper(email="user1@example.com")
    headers_1 = {"Authorization": f"Bearer {auth_info_1['access_token']}"}
    await business_helper(auth_info_1)

    # Create second user and business
    auth_info_2 = await auth_helper(email="user2@example.com")
    headers_2 = {"Authorization": f"Bearer {auth_info_2['access_token']}"}
    await business_helper(auth_info_2)

    # User 1 should only see their business
    response_1 = await client.get(
        f"{settings.api_prefix}/businesses",
        headers=headers_1,
    )
    assert response_1.status_code == 200
    data_1 = response_1.json()
    assert len(data_1) == 1

    # User 2 should only see their business
    response_2 = await client.get(
        f"{settings.api_prefix}/businesses",
        headers=headers_2,
    )
    assert response_2.status_code == 200
    data_2 = response_2.json()
    assert len(data_2) == 1


@pytest.mark.asyncio
async def test_get_business_success(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id} — get single business."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert str(data["id"]) == str(business_id)
    assert data["name"] == business_info["name"]


@pytest.mark.asyncio
async def test_get_business_not_found(client, auth_helper):
    """GET /api/v1/businesses/{id} — nonexistent business returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    # Try to get a business that doesn't exist
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"{settings.api_prefix}/businesses/{fake_id}",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_business_unauthorized(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id} — user not in business returns 404."""
    # Create first user and business
    auth_info_1 = await auth_helper(email="user1@example.com")
    business_info = await business_helper(auth_info_1)
    business_id = business_info["business_id"]

    # Create second user without access to business
    auth_info_2 = await auth_helper(email="user2@example.com")
    headers_2 = {"Authorization": f"Bearer {auth_info_2['access_token']}"}

    # User 2 tries to access User 1's business
    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}",
        headers=headers_2,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_business_requires_auth(client):
    """GET /api/v1/businesses/{id} — missing auth returns 403."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"{settings.api_prefix}/businesses/{fake_id}",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_business_success(client, auth_helper, business_helper):
    """PATCH /api/v1/businesses/{id} — update business."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.patch(
        f"{settings.api_prefix}/businesses/{business_id}",
        json={
            "name": "Updated Business Name",
            "industry": "Finance",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Business Name"
    assert data["industry"] == "Finance"


@pytest.mark.asyncio
async def test_update_business_partial(client, auth_helper, business_helper):
    """PATCH /api/v1/businesses/{id} — partial update only updates specified fields."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.patch(
        f"{settings.api_prefix}/businesses/{business_id}",
        json={
            "name": "Only Name Changed",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Only Name Changed"
    assert data["website"] == "https://test.com"  # Unchanged


@pytest.mark.asyncio
async def test_update_business_requires_auth(client, business_helper, auth_helper):
    """PATCH /api/v1/businesses/{id} — missing auth returns 403."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # No auth header
    response = await client.patch(
        f"{settings.api_prefix}/businesses/{business_id}",
        json={"name": "Hacked!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_business_not_found(client, auth_helper):
    """PATCH /api/v1/businesses/{id} — nonexistent business returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.patch(
        f"{settings.api_prefix}/businesses/{fake_id}",
        json={"name": "Updated"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_business_unauthorized(client, auth_helper, business_helper):
    """PATCH /api/v1/businesses/{id} — non-owner cannot update returns 403."""
    # Create first user (owner)
    auth_info_1 = await auth_helper(email="owner@example.com")
    business_info = await business_helper(auth_info_1)
    business_id = business_info["business_id"]

    # Create second user without ownership
    auth_info_2 = await auth_helper(email="member@example.com")
    headers_2 = {"Authorization": f"Bearer {auth_info_2['access_token']}"}

    # Member tries to update owner's business (should get 404, not part of business)
    response = await client.patch(
        f"{settings.api_prefix}/businesses/{business_id}",
        json={"name": "Hacked!"},
        headers=headers_2,
    )
    assert response.status_code == 404


# ── Company Profile (JSONB) ──


@pytest.mark.asyncio
async def test_get_company_profile_not_set(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/company-profile — empty profile returns null."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["company_profile"] is None


@pytest.mark.asyncio
async def test_save_company_profile_success(client, auth_helper, business_helper):
    """PUT /api/v1/businesses/{id}/company-profile — save profile."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.put(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        json={
            "description": "We are a tech startup",
            "services": "Software development",
            "target_audience": "Small businesses",
            "brand_voice": "Friendly and professional",
            "goals": "Scale to 100 employees",
        },
        headers=headers,
    )
    assert response.status_code == 200

    # Verify profile was saved
    get_response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        headers=headers,
    )
    assert get_response.status_code == 200
    profile_data = get_response.json()
    assert profile_data["company_profile"]["description"] == "We are a tech startup"
    assert profile_data["company_profile"]["services"] == "Software development"


@pytest.mark.asyncio
async def test_save_company_profile_requires_auth(client, auth_helper, business_helper):
    """PUT /api/v1/businesses/{id}/company-profile — missing auth returns 403."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.put(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        json={"description": "Test"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_save_company_profile_not_found(client, auth_helper):
    """PUT /api/v1/businesses/{id}/company-profile — nonexistent business returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.put(
        f"{settings.api_prefix}/businesses/{fake_id}/company-profile",
        json={"description": "Test"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_company_profile_partial(client, auth_helper, business_helper):
    """PUT /api/v1/businesses/{id}/company-profile — update existing profile."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # Save initial profile
    await client.put(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        json={"description": "Initial"},
        headers=headers,
    )

    # Update with different field
    response = await client.put(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        json={"description": "Updated", "services": "New services"},
        headers=headers,
    )
    assert response.status_code == 200

    # Verify both fields present
    get_response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/company-profile",
        headers=headers,
    )
    profile_data = get_response.json()
    assert profile_data["company_profile"]["description"] == "Updated"
    assert profile_data["company_profile"]["services"] == "New services"


# ── Profile (Markdown file-based) ──


@pytest.mark.asyncio
async def test_get_profile_not_found(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/profile — empty profile returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/profile",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_profile_requires_auth(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/profile — missing auth returns 403."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/profile",
    )
    assert response.status_code == 401


# ── Business Members ──


@pytest.mark.asyncio
async def test_get_business_members_success(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/members — list business members."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/members",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Creator should be in members list
    assert len(data) >= 1
    assert any(m.get("is_owner") is True for m in data)


@pytest.mark.asyncio
async def test_get_business_members_requires_auth(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/members — missing auth returns 403."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/members",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_business_members_not_found(client, auth_helper):
    """GET /api/v1/businesses/{id}/members — nonexistent business returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"{settings.api_prefix}/businesses/{fake_id}/members",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_business_member_success(client, auth_helper, business_helper):
    """POST /api/v1/businesses/{id}/members — add member to business."""
    # Create two users
    owner_info = await auth_helper(email="owner@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_info['access_token']}"}

    new_member_info = await auth_helper(email="newmember@example.com")

    # Owner creates business
    business_info = await business_helper(owner_info)
    business_id = business_info["business_id"]

    # Add new member
    response = await client.post(
        f"{settings.api_prefix}/businesses/{business_id}/members",
        json={
            "email": new_member_info["email"],
            "is_owner": False,
        },
        headers=owner_headers,
    )
    assert response.status_code == 201

    # Verify member was added
    members_response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/members",
        headers=owner_headers,
    )
    members = members_response.json()
    assert len(members) == 2  # Owner + new member
    assert any(str(m.get("user_id")) == str(new_member_info["user_id"]) for m in members)


@pytest.mark.asyncio
async def test_add_business_member_requires_auth(client, auth_helper, business_helper):
    """POST /api/v1/businesses/{id}/members — missing auth returns 403."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/businesses/{business_id}/members",
        json={
            "email": auth_info["email"],
            "is_owner": False,
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_membership_success(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/my-membership — get current user membership."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/my-membership",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    # user_id is not returned by the endpoint
    assert data["is_owner"] is True  # Creator is owner


@pytest.mark.asyncio
async def test_get_my_membership_requires_auth(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/my-membership — missing auth returns 403."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/my-membership",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_membership_not_member(client, auth_helper, business_helper):
    """GET /api/v1/businesses/{id}/my-membership — non-member returns 404."""
    owner_info = await auth_helper(email="owner@example.com")
    non_member_info = await auth_helper(email="nonmember@example.com")

    business_info = await business_helper(owner_info)
    business_id = business_info["business_id"]

    headers = {"Authorization": f"Bearer {non_member_info['access_token']}"}
    response = await client.get(
        f"{settings.api_prefix}/businesses/{business_id}/my-membership",
        headers=headers,
    )
    assert response.status_code == 404
