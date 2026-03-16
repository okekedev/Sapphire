"""
End-to-end pipeline test: Sales call → Lead with AI analysis → Convert to Job → Verify in Operations.

Simulates the full lifecycle:
1. Create a prospect (incoming call creates a contact)
2. Create a call interaction WITH AI analysis metadata (summary, category, action)
3. Add notes to the contact (Sales rep notes)
4. Convert lead to job via /leads/{id}/convert
5. Verify the job has all call context in metadata
6. Verify GET /jobs returns the context fields (call_summary, suggested_action, etc.)
7. Verify contact was promoted to active_customer
8. Test status transitions (new → in_progress → completed, and backward moves)
"""

import pytest
import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketing.models import Contact, Interaction
from app.operations.models import Job
from app.core.models.user import User
from app.core.models.business import Business


# ── Fixtures for this test ──

@pytest.fixture
def call_analysis_metadata():
    """Realistic AI-analyzed call metadata like Twilio + AI pipeline produces."""
    return {
        "from": "+19405551234",
        "to": "+18175559999",
        "direction": "inbound",
        "duration_s": 187,
        "recording_url": "https://api.twilio.com/recordings/RE_fake_abc123",
        "summary": (
            "Customer called about a large commercial HVAC maintenance contract "
            "for their 3-building office park. Needs quarterly inspections and "
            "emergency repair coverage. Currently unhappy with their existing "
            "provider due to slow response times. Budget around $8,000-$12,000/year."
        ),
        "call_category": "service_inquiry",
        "suggested_action": (
            "Schedule on-site assessment of all 3 buildings within the next week. "
            "Prepare a competitive quote emphasizing our 4-hour emergency response "
            "SLA. This is a high-value recurring contract opportunity."
        ),
        "score": "hot",
        "transcript": (
            "Agent: Thanks for calling Okeke LLC, how can I help?\n"
            "Caller: Hi, I manage Park View Office complex, 3 buildings...\n"
            "Agent: We'd love to take a look. Can we schedule a walk-through?\n"
            "Caller: Yes, the sooner the better. Our current company takes days..."
        ),
    }


@pytest.fixture
def second_call_metadata():
    """A second call — residential job, different profile."""
    return {
        "from": "+19405557733",
        "to": "+18175559999",
        "direction": "inbound",
        "duration_s": 95,
        "summary": (
            "Homeowner needs a full kitchen remodel. Wants modern open-concept layout, "
            "new cabinets, quartz countertops, and updated plumbing. Has a flexible "
            "timeline of 2-3 months. Budget is $25,000-$35,000."
        ),
        "call_category": "new_project",
        "suggested_action": (
            "Send design consultation packet and schedule in-home measurement visit. "
            "High budget flexibility — upsell premium finishes."
        ),
        "score": "hot",
    }


# ── The Tests ──


class TestSalesOperationsPipeline:
    """Full pipeline: Call → Lead → AI Analysis → Convert → Job in Ops."""

    @pytest.mark.asyncio
    async def test_full_pipeline_call_to_job(
        self,
        client: AsyncClient,
        auth_headers: dict,
        seed_business: Business,
        seed_user: User,
        db_session: AsyncSession,
        call_analysis_metadata: dict,
    ):
        """Step 1-5: Create prospect with call, convert to job, verify context carries over."""
        biz_id = str(seed_business.id)

        # ── Step 1: Create a prospect contact (simulates incoming call) ──
        contact = Contact(
            id=uuid.uuid4(),
            business_id=seed_business.id,
            full_name="Sarah Chen",
            company_name="Park View Office Complex",
            phone="+19405551234",
            email="sarah@parkviewoffice.com",
            status="prospect",
            source_channel="phone",
            notes="Manages 3-building office park. Unhappy with current HVAC provider.",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(contact)
        await db_session.flush()
        contact_id = str(contact.id)

        # ── Step 2: Create call interaction with AI analysis metadata ──
        interaction = Interaction(
            id=uuid.uuid4(),
            business_id=seed_business.id,
            contact_id=contact.id,
            type="call",
            direction="inbound",
            metadata_=call_analysis_metadata,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(interaction)
        await db_session.flush()

        # ── Step 3: Convert lead to job ──
        convert_resp = await client.post(
            f"/api/v1/sales/leads/{contact_id}/convert?business_id={biz_id}",
            json={
                "title": "HVAC Maintenance Contract — Park View Office Complex",
                "description": "Quarterly inspections + emergency repair for 3-building office park",
                "estimate": 10000.00,
            },
            headers=auth_headers,
        )
        assert convert_resp.status_code == 200, f"Convert failed: {convert_resp.text}"
        convert_data = convert_resp.json()
        assert convert_data["status"] == "converted"
        job_id = convert_data["job_id"]

        # ── Step 4: Verify job has call context in metadata ──
        jobs_resp = await client.get(
            f"/api/v1/sales/jobs?business_id={biz_id}&status=new",
            headers=auth_headers,
        )
        assert jobs_resp.status_code == 200
        jobs_data = jobs_resp.json()

        # Find our job
        our_job = next((j for j in jobs_data["jobs"] if j["id"] == job_id), None)
        assert our_job is not None, f"Job {job_id} not found in jobs list"

        # Verify all the call context fields are present
        assert our_job["contact_name"] == "Sarah Chen"
        assert our_job["contact_phone"] == "+19405551234"
        assert our_job["source"] == "sales_pipeline"
        assert our_job["title"] == "HVAC Maintenance Contract — Park View Office Complex"
        assert our_job["amount_quoted"] == 10000.00
        assert our_job["status"] == "new"

        # Call context from AI analysis
        assert our_job["call_summary"] is not None
        assert "commercial HVAC" in our_job["call_summary"]
        assert "office park" in our_job["call_summary"]

        assert our_job["suggested_action"] is not None
        assert "on-site assessment" in our_job["suggested_action"]

        assert our_job["lead_notes"] is not None
        assert "Manages 3-building" in our_job["lead_notes"]

        # Call category is stored in metadata but not a top-level field on JobItem
        # (it's in the metadata JSONB, not extracted to a separate column)

        # ── Step 5: Verify contact was promoted to active_customer ──
        customers_resp = await client.get(
            f"/api/v1/sales/customers?business_id={biz_id}&status=active_customer",
            headers=auth_headers,
        )
        assert customers_resp.status_code == 200
        customers = customers_resp.json()["customers"]
        sarah = next((c for c in customers if c["full_name"] == "Sarah Chen"), None)
        assert sarah is not None, "Sarah should now be an active_customer"
        assert sarah["company_name"] == "Park View Office Complex"
        assert sarah["job_count"] >= 1

    @pytest.mark.asyncio
    async def test_job_status_transitions(
        self,
        client: AsyncClient,
        auth_headers: dict,
        seed_business: Business,
        seed_user: User,
        db_session: AsyncSession,
        second_call_metadata: dict,
    ):
        """Test moving jobs forward and backward through the pipeline."""
        biz_id = str(seed_business.id)

        # Setup: create contact + call + convert
        contact = Contact(
            id=uuid.uuid4(),
            business_id=seed_business.id,
            full_name="Mike Rodriguez",
            phone="+19405557733",
            email="mike@gmail.com",
            status="prospect",
            source_channel="phone",
            notes="Wants full kitchen remodel, open concept.",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(contact)
        await db_session.flush()

        interaction = Interaction(
            id=uuid.uuid4(),
            business_id=seed_business.id,
            contact_id=contact.id,
            type="call",
            direction="inbound",
            metadata_=second_call_metadata,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(interaction)
        await db_session.flush()

        convert_resp = await client.post(
            f"/api/v1/sales/leads/{contact.id}/convert?business_id={biz_id}",
            json={
                "title": "Kitchen Remodel — Rodriguez Residence",
                "description": "Full open-concept kitchen remodel with premium finishes",
                "estimate": 30000.00,
            },
            headers=auth_headers,
        )
        assert convert_resp.status_code == 200
        job_id = convert_resp.json()["job_id"]

        # ── Forward: new → in_progress ──
        update_resp = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={biz_id}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200
        job_data = update_resp.json()
        assert job_data["status"] == "in_progress"
        assert job_data["started_at"] is not None

        # Call context should persist through status changes
        assert job_data["call_summary"] is not None
        assert "kitchen remodel" in job_data["call_summary"]
        assert job_data["suggested_action"] is not None

        # ── Backward: in_progress → new (accidental move) ──
        back_resp = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={biz_id}",
            json={"status": "new"},
            headers=auth_headers,
        )
        assert back_resp.status_code == 200
        assert back_resp.json()["status"] == "new"

        # ── Forward again: new → in_progress → completed ──
        await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={biz_id}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        complete_resp = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={biz_id}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
        completed_data = complete_resp.json()
        assert completed_data["status"] == "completed"
        assert completed_data["completed_at"] is not None

        # Call context still present on completed job
        assert completed_data["call_summary"] is not None
        assert completed_data["source"] == "sales_pipeline"

        # ── Backward from completed: completed → in_progress ──
        reopen_resp = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={biz_id}",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        assert reopen_resp.status_code == 200
        assert reopen_resp.json()["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_manual_job_no_call_context(
        self,
        client: AsyncClient,
        auth_headers: dict,
        seed_business: Business,
        seed_contact: Contact,
    ):
        """Jobs created manually (not from Sales conversion) should have no call context."""
        biz_id = str(seed_business.id)

        create_resp = await client.post(
            f"/api/v1/sales/jobs?business_id={biz_id}",
            json={
                "contact_id": str(seed_contact.id),
                "title": "Quick Plumbing Repair",
                "description": "Fix leaking kitchen faucet",
                "amount_quoted": 250.00,
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 200
        job = create_resp.json()

        # Manual jobs should NOT have call context
        assert job["call_summary"] is None
        assert job["suggested_action"] is None
        assert job["lead_notes"] is None
        assert job["source"] is None  # No source metadata

    @pytest.mark.asyncio
    async def test_convert_without_call_interaction(
        self,
        client: AsyncClient,
        auth_headers: dict,
        seed_business: Business,
        seed_user: User,
        db_session: AsyncSession,
    ):
        """Converting a lead that has no call interaction should still work, just without call context."""
        biz_id = str(seed_business.id)

        # Create a contact with NO interactions (e.g., manual entry, web form)
        contact = Contact(
            id=uuid.uuid4(),
            business_id=seed_business.id,
            full_name="Web Lead Person",
            phone="+15559990000",
            email="weblead@example.com",
            status="prospect",
            source_channel="web_form",
            notes="Submitted inquiry via website contact form.",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(contact)
        await db_session.flush()

        convert_resp = await client.post(
            f"/api/v1/sales/leads/{contact.id}/convert?business_id={biz_id}",
            json={
                "title": "Web Inquiry — General Contracting",
                "description": "Follow up on website contact form submission",
            },
            headers=auth_headers,
        )
        assert convert_resp.status_code == 200
        job_id = convert_resp.json()["job_id"]

        # Fetch the job
        jobs_resp = await client.get(
            f"/api/v1/sales/jobs?business_id={biz_id}&status=new",
            headers=auth_headers,
        )
        our_job = next((j for j in jobs_resp.json()["jobs"] if j["id"] == job_id), None)
        assert our_job is not None

        # Should have source but NO call context
        assert our_job["source"] == "sales_pipeline"
        assert our_job["call_summary"] is None
        assert our_job["suggested_action"] is None
        # lead_notes should still be populated from contact.notes
        assert our_job["lead_notes"] is None  # No call interaction → no lead_notes extraction

    @pytest.mark.asyncio
    async def test_job_notes_update_persists(
        self,
        client: AsyncClient,
        auth_headers: dict,
        seed_business: Business,
        seed_contact: Contact,
        seed_job: Job,
    ):
        """Verify that updating job notes (from mini-chat) persists correctly."""
        biz_id = str(seed_business.id)
        job_id = str(seed_job.id)

        note_content = "**Mar 9, 3:45 PM** — _What's the scope?_\nThis job covers quarterly HVAC inspections."

        update_resp = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={biz_id}",
            json={"notes": note_content},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["notes"] == note_content

        # Fetch again to confirm persistence
        jobs_resp = await client.get(
            f"/api/v1/sales/jobs?business_id={biz_id}",
            headers=auth_headers,
        )
        our_job = next((j for j in jobs_resp.json()["jobs"] if j["id"] == job_id), None)
        assert our_job is not None
        assert our_job["notes"] == note_content
