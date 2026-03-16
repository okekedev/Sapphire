"""
Tests for organization routes — departments and employees CRUD.
"""

import pytest
from uuid import UUID

from app.config import settings


# ── Departments ──


@pytest.mark.asyncio
async def test_list_departments_empty(client, auth_helper):
    """GET /api/v1/organization/departments — list with no departments returns empty list."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.get(
        f"{settings.api_prefix}/organization/departments",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_departments_requires_auth(client):
    """GET /api/v1/organization/departments — missing auth returns 401."""
    response = await client.get(
        f"{settings.api_prefix}/organization/departments",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_department_success(client, auth_helper, business_helper):
    """POST /api/v1/organization/departments — create department returns 201."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/organization/departments",
        json={
            "name": "Engineering",
            "business_id": str(business_id),
            "description": "Engineering team",
            "icon": "code",
            "display_order": 1,
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Engineering"
    assert "id" in data
    assert data["business_id"] == str(business_id)


@pytest.mark.asyncio
async def test_create_department_requires_auth(client, business_helper, auth_helper):
    """POST /api/v1/organization/departments — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/organization/departments",
        json={
            "name": "Engineering",
            "business_id": str(business_id),
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_department_missing_field(client, auth_helper, business_helper):
    """POST /api/v1/organization/departments — missing required field returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    response = await client.post(
        f"{settings.api_prefix}/organization/departments",
        json={
            # Missing name
            "business_id": str(business_id),
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_department_duplicate_name(client, auth_helper, business_helper, department_helper):
    """POST /api/v1/organization/departments — duplicate name in same business returns 400."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    # Create first department
    dept_info = await department_helper(auth_info, business_id)
    dept_name = dept_info["name"]

    # Try to create another with same name
    response = await client.post(
        f"{settings.api_prefix}/organization/departments",
        json={
            "name": dept_name,
            "business_id": str(business_id),
        },
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_department_success(client, auth_helper, business_helper, department_helper):
    """PATCH /api/v1/organization/departments/{id} — update department."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.patch(
        f"{settings.api_prefix}/organization/departments/{dept_id}",
        json={
            "name": "Engineering Team",
            "description": "Updated description",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Engineering Team"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_update_department_requires_auth(client, auth_helper, business_helper, department_helper):
    """PATCH /api/v1/organization/departments/{id} — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.patch(
        f"{settings.api_prefix}/organization/departments/{dept_id}",
        json={"name": "New Name"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_department_not_found(client, auth_helper):
    """PATCH /api/v1/organization/departments/{id} — nonexistent department returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.patch(
        f"{settings.api_prefix}/organization/departments/{fake_id}",
        json={"name": "New Name"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_department_success(client, auth_helper, business_helper, department_helper):
    """DELETE /api/v1/organization/departments/{id} — delete empty department."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.delete(
        f"{settings.api_prefix}/organization/departments/{dept_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert "deleted" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_department_requires_auth(client, auth_helper, business_helper, department_helper):
    """DELETE /api/v1/organization/departments/{id} — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.delete(
        f"{settings.api_prefix}/organization/departments/{dept_id}",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_department_not_found(client, auth_helper):
    """DELETE /api/v1/organization/departments/{id} — nonexistent department returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.delete(
        f"{settings.api_prefix}/organization/departments/{fake_id}",
        headers=headers,
    )
    assert response.status_code == 404


# ── Employees ──


@pytest.mark.asyncio
async def test_list_employees_empty(client, auth_helper):
    """GET /api/v1/organization/employees — list with no employees returns empty list."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    response = await client.get(
        f"{settings.api_prefix}/organization/employees",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_employees_requires_auth(client):
    """GET /api/v1/organization/employees — missing auth returns 401."""
    response = await client.get(
        f"{settings.api_prefix}/organization/employees",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_employee_success(client, auth_helper, business_helper, department_helper):
    """POST /api/v1/organization/employees — create employee returns 201."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "John Doe",
            "title": "Software Engineer",
            "file_stem": "john-doe",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful software engineer.",
            "model_tier": "opus",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["title"] == "Software Engineer"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_employee_requires_auth(client, auth_helper, business_helper, department_helper):
    """POST /api/v1/organization/employees — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "John Doe",
            "title": "Software Engineer",
            "file_stem": "john-doe",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful software engineer.",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_employee_missing_field(client, auth_helper, business_helper, department_helper):
    """POST /api/v1/organization/employees — missing required field returns 422."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            # Missing name
            "title": "Software Engineer",
            "file_stem": "john-doe",
            "department_id": str(dept_id),
            "business_id": str(business_id),
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_employee_invalid_department(client, auth_helper, business_helper):
    """POST /api/v1/organization/employees — invalid department_id returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    fake_dept_id = "00000000-0000-0000-0000-000000000000"

    response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "John Doe",
            "title": "Software Engineer",
            "file_stem": "john-doe",
            "department_id": fake_dept_id,
            "business_id": str(business_id),
            "system_prompt": "You are a helpful software engineer.",
        },
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_employee_success(client, auth_helper, business_helper, department_helper):
    """GET /api/v1/organization/employees/{id} — get employee with system prompt."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    # Create employee
    create_response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "Jane Smith",
            "title": "Product Manager",
            "file_stem": "jane-smith",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful product manager.",
            "model_tier": "opus",
        },
        headers=headers,
    )
    emp_id = create_response.json()["id"]

    # Get employee
    response = await client.get(
        f"{settings.api_prefix}/organization/employees/{emp_id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Jane Smith"
    assert data["title"] == "Product Manager"
    assert "system_prompt" in data


@pytest.mark.asyncio
async def test_get_employee_requires_auth(client):
    """GET /api/v1/organization/employees/{id} — missing auth returns 401."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"{settings.api_prefix}/organization/employees/{fake_id}",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_employee_not_found(client, auth_helper):
    """GET /api/v1/organization/employees/{id} — nonexistent employee returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"{settings.api_prefix}/organization/employees/{fake_id}",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_employee_success(client, auth_helper, business_helper, department_helper):
    """PATCH /api/v1/organization/employees/{id} — update employee."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    # Create employee
    create_response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "Bob Wilson",
            "title": "Developer",
            "file_stem": "bob-wilson",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful developer.",
        },
        headers=headers,
    )
    emp_id = create_response.json()["id"]

    # Update employee
    response = await client.patch(
        f"{settings.api_prefix}/organization/employees/{emp_id}",
        json={
            "title": "Senior Developer",
            "status": "inactive",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Senior Developer"
    assert data["status"] == "inactive"


@pytest.mark.asyncio
async def test_update_employee_requires_auth(client, auth_helper, business_helper, department_helper):
    """PATCH /api/v1/organization/employees/{id} — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}
    create_response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "Charlie",
            "title": "Developer",
            "file_stem": "charlie",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful developer.",
        },
        headers=headers,
    )
    emp_id = create_response.json()["id"]

    # Try to update without auth
    response = await client.patch(
        f"{settings.api_prefix}/organization/employees/{emp_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_employee_not_found(client, auth_helper):
    """PATCH /api/v1/organization/employees/{id} — nonexistent employee returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.patch(
        f"{settings.api_prefix}/organization/employees/{fake_id}",
        json={"title": "New Title"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_employee_success(client, auth_helper, business_helper, department_helper):
    """DELETE /api/v1/organization/employees/{id} — delete employee."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    # Create employee
    create_response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "Diana Prince",
            "title": "Analyst",
            "file_stem": "diana-prince",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful analyst.",
        },
        headers=headers,
    )
    emp_id = create_response.json()["id"]

    # Delete employee
    response = await client.delete(
        f"{settings.api_prefix}/organization/employees/{emp_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert "deactivated" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_employee_requires_auth(client, auth_helper, business_helper, department_helper):
    """DELETE /api/v1/organization/employees/{id} — missing auth returns 401."""
    auth_info = await auth_helper()
    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}
    create_response = await client.post(
        f"{settings.api_prefix}/organization/employees",
        json={
            "name": "Eve",
            "title": "Designer",
            "file_stem": "eve",
            "department_id": str(dept_id),
            "business_id": str(business_id),
            "system_prompt": "You are a helpful designer.",
        },
        headers=headers,
    )
    emp_id = create_response.json()["id"]

    # Try to delete without auth
    response = await client.delete(
        f"{settings.api_prefix}/organization/employees/{emp_id}",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_employee_not_found(client, auth_helper):
    """DELETE /api/v1/organization/employees/{id} — nonexistent employee returns 404."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.delete(
        f"{settings.api_prefix}/organization/employees/{fake_id}",
        headers=headers,
    )
    assert response.status_code == 404


# ── Org Chart ──


@pytest.mark.asyncio
async def test_get_org_chart_success(client, auth_helper, business_helper, department_helper):
    """GET /api/v1/organization/org-chart — get org chart."""
    auth_info = await auth_helper()
    headers = {"Authorization": f"Bearer {auth_info['access_token']}"}

    business_info = await business_helper(auth_info)
    business_id = business_info["business_id"]

    dept_info = await department_helper(auth_info, business_id)
    dept_id = dept_info["department_id"]

    # Create some employees
    for i in range(2):
        await client.post(
            f"{settings.api_prefix}/organization/employees",
            json={
                "name": f"Employee {i}",
                "title": "Engineer",
                "file_stem": f"emp-{i}",
                "department_id": str(dept_id),
                "business_id": str(business_id),
                "system_prompt": "You are a helpful engineer.",
            },
            headers=headers,
        )

    response = await client.get(
        f"{settings.api_prefix}/organization/org-chart?business_id={business_id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_org_chart_requires_auth(client):
    """GET /api/v1/organization/org-chart — missing auth returns 401."""
    response = await client.get(
        f"{settings.api_prefix}/organization/org-chart",
    )
    assert response.status_code == 401
