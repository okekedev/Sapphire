"""
Comprehensive tests for the marketing phone lines router.

Tests cover:
  - GET /api/v1/phone-lines — list phone lines
  - POST /api/v1/phone-lines — create phone line
  - PATCH /api/v1/phone-lines/{id} — update phone line
  - DELETE /api/v1/phone-lines/{id} — delete phone line
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.business import Business
from app.marketing.models import BusinessPhoneLine


# ── GET /phone-lines ──

@pytest.mark.asyncio
async def test_list_phone_lines_happy_path(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test listing phone lines for a business."""
    # Create phone lines
    tn1 = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15551234567",
        twilio_number_sid="PNabcdef123456",
        friendly_name="Main Office",
        campaign_name="Google Ads",
        channel="paid_search",
        line_type="mainline",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    tn2 = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15559876543",
        twilio_number_sid="PNxyzabc789012",
        friendly_name="Marketing Campaign",
        campaign_name="Facebook Ads",
        channel="social_media",
        line_type="tracking",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn1)
    db_session.add(tn2)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["twilio_number"] == "+15559876543"  # Most recent first
    assert data[1]["twilio_number"] == "+15551234567"


@pytest.mark.asyncio
async def test_list_phone_lines_empty(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test listing phone lines when none exist."""
    response = await client.get(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_phone_lines_unauthorized(
    client: AsyncClient,
    seed_business: Business,
):
    """Test that listing phone lines without auth returns 401."""
    response = await client.get(
        f"/api/v1/phone-lines?business_id={seed_business.id}"
    )
    assert response.status_code == 401


# ── POST /phone-lines ──

@pytest.mark.asyncio
async def test_create_phone_line_happy_path(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test creating a new phone line."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15551234567",
            "twilio_number_sid": "PNabcdef123456",
            "friendly_name": "Main Office Line",
            "campaign_name": "Google Ads - Dallas",
            "channel": "paid_search",
            "line_type": "mainline",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["twilio_number"] == "+15551234567"
    assert data["friendly_name"] == "Main Office Line"
    assert data["campaign_name"] == "Google Ads - Dallas"
    assert data["channel"] == "paid_search"
    assert data["line_type"] == "mainline"
    assert data["active"] is True
    assert data["business_id"] == str(seed_business.id)


@pytest.mark.asyncio
async def test_create_phone_line_facebook_ads(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test creating a phone line for Facebook Ads campaign."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15559876543",
            "campaign_name": "Facebook Summer Sale",
            "channel": "social_media",
            "ad_account_id": "act_123456789",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["campaign_name"] == "Facebook Summer Sale"
    assert data["channel"] == "social_media"
    assert data["ad_account_id"] == "act_123456789"


@pytest.mark.asyncio
async def test_create_phone_line_organic(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test creating a phone line for organic/direct calls."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15555551111",
            "campaign_name": "Direct/Organic",
            "channel": "organic",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["campaign_name"] == "Direct/Organic"
    assert data["channel"] == "organic"


@pytest.mark.asyncio
async def test_create_phone_line_with_department(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    seed_department,
):
    """Test creating a phone line linked to a department."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15552223333",
            "campaign_name": "Sales Department Line",
            "channel": "direct",
            "department_id": str(seed_department.id),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["campaign_name"] == "Sales Department Line"
    assert data["department_id"] == str(seed_department.id)


@pytest.mark.asyncio
async def test_create_phone_line_minimal(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test creating a phone line with minimal required fields."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15556667777",
            "campaign_name": "Minimal Campaign",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["twilio_number"] == "+15556667777"
    assert data["campaign_name"] == "Minimal Campaign"
    assert data["line_type"] == "tracking"
    assert data["active"] is True


@pytest.mark.asyncio
async def test_create_phone_line_missing_twilio_number(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test that creating without twilio_number fails validation."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "campaign_name": "Missing Phone",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_phone_line_missing_campaign_name(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test that creating without campaign_name fails validation."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15551111111",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_phone_line_unauthorized(
    client: AsyncClient,
    seed_business: Business,
):
    """Test that creating a phone line without auth returns 401."""
    response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        json={
            "twilio_number": "+15551234567",
            "campaign_name": "Unauthorized Campaign",
        },
    )
    assert response.status_code == 401


# ── PATCH /phone-lines/{id} ──

@pytest.mark.asyncio
async def test_update_phone_line_happy_path(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test updating a phone line."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15551234567",
        campaign_name="Original Campaign",
        channel="paid_search",
        line_type="tracking",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "campaign_name": "Updated Campaign",
            "friendly_name": "Updated Label",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["campaign_name"] == "Updated Campaign"
    assert data["friendly_name"] == "Updated Label"
    # Original fields should persist
    assert data["twilio_number"] == "+15551234567"


@pytest.mark.asyncio
async def test_update_phone_line_channel(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test updating the channel of a phone line."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15559876543",
        campaign_name="Campaign",
        channel="organic",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={"channel": "paid_search"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["channel"] == "paid_search"


@pytest.mark.asyncio
async def test_update_phone_line_deactivate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test deactivating a phone line."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15552221111",
        campaign_name="Campaign",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={"active": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is False


@pytest.mark.asyncio
async def test_update_phone_line_mark_mainline(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test marking a phone line as mainline."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15553334444",
        campaign_name="Campaign",
        line_type="tracking",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={"line_type": "mainline"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["line_type"] == "mainline"


@pytest.mark.asyncio
async def test_update_phone_line_set_department(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    seed_department,
    db_session: AsyncSession,
):
    """Test assigning a phone line to a department."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15554445555",
        campaign_name="Campaign",
        department_id=None,
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={"department_id": str(seed_department.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["department_id"] == str(seed_department.id)


@pytest.mark.asyncio
async def test_update_phone_line_partial(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test partial update of a phone line."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15555556666",
        campaign_name="Original",
        channel="organic",
        ad_account_id="act_old123",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={"ad_account_id": "act_new456"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ad_account_id"] == "act_new456"
    # Other fields unchanged
    assert data["campaign_name"] == "Original"
    assert data["channel"] == "organic"


@pytest.mark.asyncio
async def test_update_phone_line_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test updating a non-existent phone line returns 404."""
    fake_id = uuid.uuid4()
    response = await client.patch(
        f"/api/v1/phone-lines/{fake_id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={"campaign_name": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_phone_line_unauthorized(
    client: AsyncClient,
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test that updating a phone line without auth returns 401."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15556667777",
        campaign_name="Campaign",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}",
        json={"campaign_name": "Updated"},
    )
    assert response.status_code == 401


# ── DELETE /phone-lines/{id} ──

@pytest.mark.asyncio
async def test_delete_phone_line_happy_path(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test deleting a phone line."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15551112222",
        campaign_name="Campaign to Delete",
        active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    phone_line_id = tn.id

    response = await client.delete(
        f"/api/v1/phone-lines/{phone_line_id}?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    # Verify the phone line is deleted
    result = await db_session.execute(
        select(BusinessPhoneLine).where(BusinessPhoneLine.id == phone_line_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_phone_line_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test deleting a non-existent phone line returns 404."""
    fake_id = uuid.uuid4()
    response = await client.delete(
        f"/api/v1/phone-lines/{fake_id}?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_phone_line_unauthorized(
    client: AsyncClient,
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test that deleting a phone line without auth returns 401."""
    tn = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15552223333",
        campaign_name="Campaign",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn)
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/phone-lines/{tn.id}?business_id={seed_business.id}"
    )
    assert response.status_code == 401


# ── Cross-endpoint tests ──

@pytest.mark.asyncio
async def test_phone_line_isolation_by_business(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
    db_session: AsyncSession,
):
    """Test that phone lines are isolated by business."""
    # Create another business
    from app.core.models.business import Business as BusinessModel
    other_biz = BusinessModel(
        id=uuid.uuid4(),
        name="Other Business",
        website="https://other.com",
        created_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_biz)
    await db_session.commit()

    # Create phone lines for each business
    tn_seed = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=seed_business.id,
        twilio_number="+15551111111",
        campaign_name="Seed Business Campaign",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    tn_other = BusinessPhoneLine(
        id=uuid.uuid4(),
        business_id=other_biz.id,
        twilio_number="+15552222222",
        campaign_name="Other Business Campaign",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tn_seed)
    db_session.add(tn_other)
    await db_session.commit()

    # Query for seed business should only return its phone line
    response = await client.get(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["campaign_name"] == "Seed Business Campaign"


@pytest.mark.asyncio
async def test_create_then_update_then_delete(
    client: AsyncClient,
    auth_headers: dict[str, str],
    seed_business: Business,
):
    """Test full lifecycle: create, update, delete."""
    # Create
    create_response = await client.post(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "twilio_number": "+15553334444",
            "campaign_name": "Lifecycle Campaign",
            "channel": "organic",
        },
    )
    assert create_response.status_code == 201
    phone_line_id = create_response.json()["id"]

    # Update
    update_response = await client.patch(
        f"/api/v1/phone-lines/{phone_line_id}?business_id={seed_business.id}",
        headers=auth_headers,
        json={
            "campaign_name": "Updated Lifecycle Campaign",
            "line_type": "mainline",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["campaign_name"] == "Updated Lifecycle Campaign"
    assert update_response.json()["line_type"] == "mainline"

    # Delete
    delete_response = await client.delete(
        f"/api/v1/phone-lines/{phone_line_id}?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    # Verify deletion via list
    list_response = await client.get(
        f"/api/v1/phone-lines?business_id={seed_business.id}",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 0
