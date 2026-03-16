"""
Comprehensive tests for Sales department routes.
Tests all customer, job, and summary endpoints.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestGetCustomers:
    """Tests for GET /api/v1/sales/customers"""

    @pytest.mark.asyncio
    async def test_get_customers_success(self, client: AsyncClient, auth_headers: dict, seed_business, db_session: AsyncSession):
        """Successfully retrieve customers for a business"""
        response = await client.get(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "customers" in data
        assert "total" in data
        assert isinstance(data["customers"], list)
        assert isinstance(data["total"], int)

    @pytest.mark.asyncio
    async def test_get_customers_empty_list(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Return empty list when no customers exist"""
        response = await client.get(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["customers"] == []

    @pytest.mark.asyncio
    async def test_get_customers_with_seed_data(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact, db_session: AsyncSession):
        """Retrieve customers including seeded customer data"""
        response = await client.get(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["customers"]) >= 1
        
        # Verify customer fields
        customer = data["customers"][0]
        assert "id" in customer
        assert "full_name" in customer
        assert "email" in customer
        assert "phone" in customer
        assert "status" in customer
        assert "created_at" in customer

    @pytest.mark.asyncio
    async def test_get_customers_missing_business_id(self, client: AsyncClient, auth_headers: dict):
        """Return 422 when business_id query param is missing"""
        response = await client.get(
            "/api/v1/sales/customers",
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_customers_invalid_business_id(self, client: AsyncClient, auth_headers: dict):
        """Return 422 with invalid business_id format"""
        response = await client.get(
            f"/api/v1/sales/customers?business_id=invalid-uuid",
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_customers_unauthorized(self, client: AsyncClient, seed_business):
        """Return 401 without authentication headers"""
        response = await client.get(
            f"/api/v1/sales/customers?business_id={seed_business.id}"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_customers_filter_by_status(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact, db_session: AsyncSession):
        """Filter customers by status"""
        # Create customers with different statuses
        from app.marketing.models import Contact

        cust1 = Contact(
            business_id=seed_business.id,
            full_name="Prospect Customer",
            email="prospect@test.com",
            phone="+1234567890",
            status="prospect"
        )
        cust2 = Contact(
            business_id=seed_business.id,
            full_name="Converted Customer",
            email="converted@test.com",
            phone="+0987654321",
            status="active_customer"
        )
        db_session.add(cust1)
        db_session.add(cust2)
        await db_session.commit()
        
        # Query prospects
        response = await client.get(
            f"/api/v1/sales/customers?business_id={seed_business.id}&status=prospect",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        prospects = [c for c in data["customers"] if c["status"] == "prospect"]
        assert len(prospects) >= 1


class TestCreateCustomer:
    """Tests for POST /api/v1/sales/customers"""

    @pytest.mark.asyncio
    async def test_create_customer_success(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Successfully create a new customer"""
        payload = {
            "full_name": "John Doe",
            "phone": "+1234567890",
            "email": "john@example.com",
            "status": "prospect"
        }
        response = await client.post(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "John Doe"
        assert data["email"] == "john@example.com"
        assert data["phone"] == "+1234567890"
        assert data["status"] == "prospect"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_customer_with_notes(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Create customer with optional notes field"""
        payload = {
            "full_name": "Jane Smith",
            "phone": "+0987654321",
            "email": "jane@example.com",
            "status": "prospect",
            "notes": "Hot lead from referral"
        }
        response = await client.post(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Hot lead from referral"

    @pytest.mark.asyncio
    async def test_create_customer_missing_field(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Create customer with optional phone (will succeed since it's optional)"""
        payload = {
            "full_name": "Incomplete",
            "email": "incomplete@example.com"
            # Missing phone - but it's optional, status defaults to "prospect"
        }
        response = await client.post(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        # This should succeed since phone is optional and status has a default
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_customer_missing_business_id(self, client: AsyncClient, auth_headers: dict):
        """Return 422 when business_id is missing"""
        payload = {
            "full_name": "John Doe",
            "phone": "+1234567890",
            "email": "john@example.com",
            "status": "prospect"
        }
        response = await client.post(
            "/api/v1/sales/customers",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_customer_unauthorized(self, client: AsyncClient, seed_business):
        """Return 401 without authentication"""
        payload = {
            "full_name": "John Doe",
            "phone": "+1234567890",
            "email": "john@example.com",
            "status": "prospect"
        }
        response = await client.post(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            json=payload
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_customer_invalid_status(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Create customer with any status value (no validation)"""
        payload = {
            "full_name": "John Doe",
            "phone": "+1234567890",
            "email": "john@example.com",
            "status": "invalid_status"
        }
        response = await client.post(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        # Status is not validated, so this succeeds
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_customer_duplicate_email(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Allow multiple customers (no unique email constraint)"""
        # First customer created via seed_contact
        payload = {
            "full_name": "Same Email Customer",
            "phone": "+1111111111",
            "email": seed_contact.email,  # Same email as seed_contact
            "status": "prospect"
        }
        response = await client.post(
            f"/api/v1/sales/customers?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        # Should succeed as there's no unique constraint on email
        assert response.status_code == 200


class TestUpdateCustomer:
    """Tests for PATCH /api/v1/sales/customers/{id}"""

    @pytest.mark.asyncio
    async def test_update_customer_success(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Successfully update customer fields"""
        customer_id = str(seed_contact.id)
        payload = {
            "status": "customer",
            "notes": "Updated notes"
        }
        response = await client.patch(
            f"/api/v1/sales/customers/{customer_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # When status is set to "customer", it gets converted to "active_customer"
        assert data["status"] == "active_customer"
        assert data["notes"] == "Updated notes"

    @pytest.mark.asyncio
    async def test_update_customer_partial_fields(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Update only some fields"""
        customer_id = str(seed_contact.id)
        payload = {"full_name": "Updated Name"}
        response = await client.patch(
            f"/api/v1/sales/customers/{customer_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_customer_not_found(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Return 404 when customer not found"""
        fake_id = str(uuid4())
        payload = {"status": "customer"}
        response = await client.patch(
            f"/api/v1/sales/customers/{fake_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_customer_unauthorized(self, client: AsyncClient, seed_business, seed_contact):
        """Return 401 without authentication"""
        customer_id = str(seed_contact.id)
        payload = {"status": "customer"}
        response = await client.patch(
            f"/api/v1/sales/customers/{customer_id}?business_id={seed_business.id}",
            json=payload
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_customer_invalid_business_id(self, client: AsyncClient, auth_headers: dict, seed_contact):
        """Return 422 with invalid business_id"""
        customer_id = str(seed_contact.id)
        payload = {"status": "customer"}
        response = await client.patch(
            f"/api/v1/sales/customers/{customer_id}?business_id=invalid",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_customer_wrong_business(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Return 404 when customer belongs to different business"""
        customer_id = str(seed_contact.id)
        other_business_id = str(uuid4())
        payload = {"status": "customer"}
        response = await client.patch(
            f"/api/v1/sales/customers/{customer_id}?business_id={other_business_id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 404


class TestGetJobs:
    """Tests for GET /api/v1/sales/jobs"""

    @pytest.mark.asyncio
    async def test_get_jobs_success(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Successfully retrieve jobs for a business"""
        response = await client.get(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert isinstance(data["jobs"], list)
        assert isinstance(data["total"], int)

    @pytest.mark.asyncio
    async def test_get_jobs_empty_list(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Return empty list when no jobs exist"""
        response = await client.get(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["jobs"] == []

    @pytest.mark.asyncio
    async def test_get_jobs_with_seed_data(self, client: AsyncClient, auth_headers: dict, seed_business, seed_job, db_session: AsyncSession):
        """Retrieve jobs including seeded job data"""
        response = await client.get(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["jobs"]) >= 1
        
        # Verify job fields
        job = data["jobs"][0]
        assert "id" in job
        assert "contact_id" in job
        assert "contact_name" in job
        assert "title" in job
        assert "description" in job
        assert "status" in job
        assert "amount_quoted" in job
        assert "created_at" in job

    @pytest.mark.asyncio
    async def test_get_jobs_missing_business_id(self, client: AsyncClient, auth_headers: dict):
        """Return 422 when business_id is missing"""
        response = await client.get(
            "/api/v1/sales/jobs",
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_jobs_unauthorized(self, client: AsyncClient, seed_business):
        """Return 401 without authentication"""
        response = await client.get(
            f"/api/v1/sales/jobs?business_id={seed_business.id}"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_jobs_filter_by_status(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact, db_session: AsyncSession):
        """Filter jobs by status"""
        from app.operations.models import Job

        job1 = Job(
            business_id=seed_business.id,
            contact_id=seed_contact.id,
            title="Active Job",
            description="In progress",
            status="in_progress",
            amount_quoted=1000.00,
            created_by=None
        )
        job2 = Job(
            business_id=seed_business.id,
            contact_id=seed_contact.id,
            title="Completed Job",
            description="Done",
            status="completed",
            amount_quoted=500.00,
            created_by=None
        )
        db_session.add(job1)
        db_session.add(job2)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/sales/jobs?business_id={seed_business.id}&status=completed",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        completed_jobs = [j for j in data["jobs"] if j["status"] == "completed"]
        assert len(completed_jobs) >= 1


class TestCreateJob:
    """Tests for POST /api/v1/sales/jobs"""

    @pytest.mark.asyncio
    async def test_create_job_success(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Successfully create a new job"""
        payload = {
            "contact_id": str(seed_contact.id),
            "title": "Website Redesign",
            "description": "Complete redesign of company website",
            "amount_quoted": 5000.00
        }
        response = await client.post(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Website Redesign"
        assert data["contact_id"] == str(seed_contact.id)
        assert data["amount_quoted"] == 5000.00
        assert "id" in data
        assert "status" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_job_with_notes(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Create job with optional notes"""
        payload = {
            "contact_id": str(seed_contact.id),
            "title": "Logo Design",
            "description": "New company logo",
            "amount_quoted": 2000.00,
            "notes": "Client wants modern minimalist style"
        }
        response = await client.post(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Client wants modern minimalist style"

    @pytest.mark.asyncio
    async def test_create_job_missing_field(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Create job with optional description and amount (will succeed)"""
        payload = {
            "contact_id": str(seed_contact.id),
            "title": "Incomplete Job"
            # Missing description and amount_quoted - these are optional
        }
        response = await client.post(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        # This should succeed since description and amount_quoted are optional
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_job_invalid_contact(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Return 404 when contact doesn't exist"""
        fake_contact_id = str(uuid4())
        payload = {
            "contact_id": fake_contact_id,
            "title": "Job for Missing Contact",
            "description": "This should fail",
            "amount_quoted": 1000.00
        }
        response = await client.post(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_job_unauthorized(self, client: AsyncClient, seed_business, seed_contact):
        """Return 401 without authentication"""
        payload = {
            "contact_id": str(seed_contact.id),
            "title": "Unauthorized Job",
            "description": "Should fail",
            "amount_quoted": 1000.00
        }
        response = await client.post(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            json=payload
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_job_zero_amount(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact):
        """Create job with zero quoted amount"""
        payload = {
            "contact_id": str(seed_contact.id),
            "title": "Free Job",
            "description": "No charge",
            "amount_quoted": 0.00
        }
        response = await client.post(
            f"/api/v1/sales/jobs?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Zero amount is converted to None by the router
        assert data["amount_quoted"] is None


class TestUpdateJob:
    """Tests for PATCH /api/v1/sales/jobs/{id}"""

    @pytest.mark.asyncio
    async def test_update_job_success(self, client: AsyncClient, auth_headers: dict, seed_business, seed_job):
        """Successfully update job fields"""
        job_id = str(seed_job.id)
        payload = {
            "status": "completed",
            "amount_billed": 5000.00
        }
        response = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["amount_billed"] == 5000.00

    @pytest.mark.asyncio
    async def test_update_job_status_transition(self, client: AsyncClient, auth_headers: dict, seed_business, seed_job):
        """Test valid job status transitions"""
        job_id = str(seed_job.id)
        
        # Move from draft to active
        payload = {"status": "active"}
        response = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_update_job_partial_fields(self, client: AsyncClient, auth_headers: dict, seed_business, seed_job):
        """Update only some fields"""
        job_id = str(seed_job.id)
        payload = {"notes": "Updated notes"}
        response = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Updated notes"

    @pytest.mark.asyncio
    async def test_update_job_not_found(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Return 404 when job not found"""
        fake_id = str(uuid4())
        payload = {"status": "completed"}
        response = await client.patch(
            f"/api/v1/sales/jobs/{fake_id}?business_id={seed_business.id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_job_unauthorized(self, client: AsyncClient, seed_business, seed_job):
        """Return 401 without authentication"""
        job_id = str(seed_job.id)
        payload = {"status": "completed"}
        response = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={seed_business.id}",
            json=payload
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_job_wrong_business(self, client: AsyncClient, auth_headers: dict, seed_business, seed_job):
        """Return 404 when job belongs to different business"""
        job_id = str(seed_job.id)
        other_business_id = str(uuid4())
        payload = {"status": "completed"}
        response = await client.patch(
            f"/api/v1/sales/jobs/{job_id}?business_id={other_business_id}",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 404


class TestSalesSummary:
    """Tests for GET /api/v1/sales/summary"""

    @pytest.mark.asyncio
    async def test_get_summary_success(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Successfully retrieve sales summary"""
        response = await client.get(
            f"/api/v1/sales/summary?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_prospects" in data
        assert "total_customers" in data
        assert "total_no_conversion" in data
        assert "active_jobs" in data
        assert "completed_jobs" in data
        assert "total_revenue" in data
        assert "total_quoted" in data

    @pytest.mark.asyncio
    async def test_summary_has_correct_types(self, client: AsyncClient, auth_headers: dict, seed_business):
        """Verify summary fields have correct types"""
        response = await client.get(
            f"/api/v1/sales/summary?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["total_prospects"], int)
        assert isinstance(data["total_customers"], int)
        assert isinstance(data["total_no_conversion"], int)
        assert isinstance(data["active_jobs"], int)
        assert isinstance(data["completed_jobs"], int)
        assert isinstance(data["total_revenue"], (int, float))
        assert isinstance(data["total_quoted"], (int, float))

    @pytest.mark.asyncio
    async def test_summary_with_data(self, client: AsyncClient, auth_headers: dict, seed_business, seed_contact, seed_job, db_session: AsyncSession):
        """Get summary with populated data"""
        response = await client.get(
            f"/api/v1/sales/summary?business_id={seed_business.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should have at least the seeded data
        assert data["total_customers"] >= 1 or data["total_prospects"] >= 1
        assert data["active_jobs"] >= 0
        assert data["completed_jobs"] >= 0

    @pytest.mark.asyncio
    async def test_summary_missing_business_id(self, client: AsyncClient, auth_headers: dict):
        """Return 422 when business_id is missing"""
        response = await client.get(
            "/api/v1/sales/summary",
            headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_summary_unauthorized(self, client: AsyncClient, seed_business):
        """Return 401 without authentication"""
        response = await client.get(
            f"/api/v1/sales/summary?business_id={seed_business.id}"
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_summary_invalid_business_id(self, client: AsyncClient, auth_headers: dict):
        """Return 422 with invalid business_id format"""
        response = await client.get(
            f"/api/v1/sales/summary?business_id=invalid-uuid",
            headers=auth_headers
        )
        assert response.status_code == 422
