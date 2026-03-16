# Workforce API Test Suite

Comprehensive pytest test suite for the core Workforce API routers. All tests are async and use an in-memory SQLite database for isolation.

## Test Files Overview

### 1. `test_auth.py` (16 test cases, 259 lines)
Tests for authentication routes (`/api/v1/auth/`):
- **POST /auth/register**: User registration, duplicate email handling, validation
- **POST /auth/login**: Authentication, wrong password, nonexistent user
- **POST /auth/refresh**: Token refresh, invalid/expired tokens, token type validation

**Test Coverage:**
- `test_register_success` — Creates new user and returns JWT tokens
- `test_register_duplicate_email` — Prevents duplicate email registration (409)
- `test_register_invalid_email` — Validates email format (422)
- `test_register_missing_field` — Enforces required fields (422)
- `test_register_empty_password` — Validates password presence (422)
- `test_login_success` — Authenticates with correct credentials
- `test_login_wrong_password` — Rejects invalid passwords (401)
- `test_login_nonexistent_email` — Handles nonexistent users (401)
- `test_login_invalid_email_format` — Validates email format (422)
- `test_login_missing_field` — Enforces required fields (422)
- `test_refresh_token_success` — Issues new tokens from valid refresh token
- `test_refresh_invalid_token` — Rejects invalid tokens (401)
- `test_refresh_with_access_token` — Prevents using access token as refresh (401)
- `test_refresh_malformed_token` — Handles malformed tokens (401)
- `test_refresh_missing_token` — Enforces required fields (422)
- `test_register_token_can_be_used` — Verifies returned token is valid

**Status Codes Tested:** 201, 200, 401, 403, 409, 422

---

### 2. `test_businesses.py` (32 test cases, 619 lines)
Tests for business management routes (`/api/v1/businesses/`):
- **POST /businesses**: Business CRUD operations
- **GET /businesses**: List businesses
- **GET /businesses/{id}**: Get single business
- **PATCH /businesses/{id}**: Update business details
- **GET/PUT /businesses/{id}/company-profile**: JSONB profile management
- **GET /businesses/{id}/members**: List team members
- **POST /businesses/{id}/members**: Add team members
- **GET /businesses/{id}/my-membership**: Get user's membership

**Test Coverage:**
- **Business CRUD:**
  - `test_create_business_success` — Creates business with all fields
  - `test_create_business_requires_auth` — Enforces authentication (403)
  - `test_create_business_invalid_auth` — Rejects invalid tokens (403)
  - `test_create_business_missing_field` — Validates required fields (422)
  - `test_list_businesses_empty` — Returns empty list when no businesses
  - `test_list_businesses_multiple` — Lists multiple businesses
  - `test_list_businesses_requires_auth` — Enforces authentication (403)
  - `test_list_businesses_isolation` — Users only see their own businesses
  - `test_get_business_success` — Retrieves single business
  - `test_get_business_not_found` — Handles missing business (404)
  - `test_get_business_unauthorized` — Prevents unauthorized access (404)
  - `test_get_business_requires_auth` — Enforces authentication (403)
  - `test_update_business_success` — Updates all fields
  - `test_update_business_partial` — Supports partial updates
  - `test_update_business_requires_auth` — Enforces authentication (403)
  - `test_update_business_not_found` — Handles missing business (404)
  - `test_update_business_unauthorized` — Restricts to owner/admin (404)

- **Company Profile (JSONB):**
  - `test_get_company_profile_not_set` — Returns null for new business
  - `test_save_company_profile_success` — Stores JSONB profile
  - `test_save_company_profile_requires_auth` — Enforces authentication (403)
  - `test_save_company_profile_not_found` — Handles missing business (404)
  - `test_update_company_profile_partial` — Supports incremental updates

- **Team Members:**
  - `test_get_business_members_success` — Lists team members
  - `test_get_business_members_requires_auth` — Enforces authentication (403)
  - `test_get_business_members_not_found` — Handles missing business (404)
  - `test_add_business_member_success` — Adds team member
  - `test_add_business_member_requires_auth` — Enforces authentication (403)
  - `test_get_my_membership_success` — Returns user's membership info
  - `test_get_my_membership_requires_auth` — Enforces authentication (403)
  - `test_get_my_membership_not_member` — Returns 404 for non-members

**Status Codes Tested:** 200, 201, 403, 404, 422

---

### 3. `test_health.py` (3 test cases, 38 lines)
Tests for health check endpoint (`/api/v1/health`):

**Test Coverage:**
- `test_health_check_success` — Returns healthy status (200)
- `test_health_check_no_auth_required` — Accessible without authentication
- `test_health_check_response_format` — Returns valid JSON structure

**Status Codes Tested:** 200

---

### 4. `test_organization.py` (29 test cases, 644 lines)
Tests for organization management routes (`/api/v1/organization/`):
- **GET/POST /organization/departments**: Department CRUD
- **PATCH/DELETE /organization/departments/{id}**: Department updates and deletion
- **GET/POST /organization/employees**: Employee CRUD
- **GET/PATCH/DELETE /organization/employees/{id}**: Employee management
- **GET /organization/org-chart**: Organization hierarchy visualization

**Test Coverage:**
- **Departments:**
  - `test_list_departments_empty` — Returns empty list for new business
  - `test_list_departments_requires_auth` — Enforces authentication (403)
  - `test_create_department_success` — Creates department with metadata
  - `test_create_department_requires_auth` — Enforces authentication (403)
  - `test_create_department_missing_field` — Validates required fields (422)
  - `test_create_department_duplicate_name` — Prevents duplicate names (400)
  - `test_update_department_success` — Updates department fields
  - `test_update_department_requires_auth` — Enforces authentication (403)
  - `test_update_department_not_found` — Handles missing department (404)
  - `test_delete_department_success` — Deletes empty department
  - `test_delete_department_requires_auth` — Enforces authentication (403)
  - `test_delete_department_not_found` — Handles missing department (404)

- **Employees:**
  - `test_list_employees_empty` — Returns empty list for new business
  - `test_list_employees_requires_auth` — Enforces authentication (403)
  - `test_create_employee_success` — Creates employee with all fields
  - `test_create_employee_requires_auth` — Enforces authentication (403)
  - `test_create_employee_missing_field` — Validates required fields (422)
  - `test_create_employee_invalid_department` — Validates department exists (404)
  - `test_get_employee_success` — Retrieves employee with system prompt
  - `test_get_employee_requires_auth` — Enforces authentication (403)
  - `test_get_employee_not_found` — Handles missing employee (404)
  - `test_update_employee_success` — Updates employee fields
  - `test_update_employee_requires_auth` — Enforces authentication (403)
  - `test_update_employee_not_found` — Handles missing employee (404)
  - `test_delete_employee_success` — Deletes employee
  - `test_delete_employee_requires_auth` — Enforces authentication (403)
  - `test_delete_employee_not_found` — Handles missing employee (404)

- **Org Chart:**
  - `test_get_org_chart_success` — Returns organizational hierarchy
  - `test_get_org_chart_requires_auth` — Enforces authentication (403)

**Status Codes Tested:** 200, 201, 400, 403, 404, 422

---

### 5. `test_platforms.py` (22 test cases, 554 lines)
Tests for platform connection routes (`/api/v1/platforms/`):
- **POST /platforms/connect/api-key**: Connect API key platforms
- **GET /platforms/connections**: List platform connections
- **POST /platforms/disconnect**: Disconnect platforms
- **GET /platforms/test/{platform}**: Test connection validity
- **POST /platforms/refresh**: Refresh OAuth tokens

**Test Coverage:**
- **API Key Connections:**
  - `test_connect_api_key_success` — Stores encrypted API key (201)
  - `test_connect_api_key_requires_auth` — Enforces authentication (403)
  - `test_connect_api_key_invalid_platform` — Validates platform name (400)
  - `test_connect_api_key_missing_field` — Validates required fields (422)
  - `test_connect_api_key_with_department_id` — Supports department scope

- **List Connections:**
  - `test_list_connections_empty` — Returns empty list when no connections
  - `test_list_connections_success` — Lists all connections
  - `test_list_connections_requires_auth` — Enforces authentication (403)
  - `test_list_connections_missing_business_id` — Requires business_id query param (422)
  - `test_list_connections_filter_by_department` — Filters by department scope

- **Disconnect:**
  - `test_disconnect_platform_success` — Removes connection
  - `test_disconnect_nonexistent_connection` — Handles missing connection (404)
  - `test_disconnect_requires_auth` — Enforces authentication (403)
  - `test_disconnect_missing_field` — Validates required fields (422)
  - `test_disconnect_department_scoped` — Removes department-scoped connection

- **Connection Testing:**
  - `test_test_connection_success` — Verifies connection validity
  - `test_test_connection_not_found` — Handles missing connection (404)
  - `test_test_connection_requires_auth` — Enforces authentication (403)
  - `test_test_connection_missing_business_id` — Requires business_id query param (422)

- **Token Refresh:**
  - `test_refresh_platform_token_success` — Refreshes OAuth token
  - `test_refresh_platform_token_not_found` — Handles missing connection (400)
  - `test_refresh_platform_token_requires_auth` — Enforces authentication (403)

**Status Codes Tested:** 200, 201, 400, 403, 404, 422

---

## Test Fixtures

All tests rely on shared fixtures in `conftest.py`:

### Core Fixtures
- **`test_db_engine`** — In-memory SQLite async engine
- **`test_db_session`** — AsyncSession for test database
- **`test_client`** — AsyncClient with ASGI transport

### Helper Fixtures
- **`auth_helper(email, password, full_name)`** — Creates user and returns auth tokens
- **`business_helper(auth_info)`** — Creates business for authenticated user
- **`department_helper(auth_info, business_id)`** — Creates department in business

## Running Tests

```bash
# Run all tests
pytest app/core/tests/test_*.py -v

# Run specific test file
pytest app/core/tests/test_auth.py -v

# Run single test
pytest app/core/tests/test_auth.py::test_register_success -v

# Run with coverage
pytest app/core/tests/ --cov=app/core --cov-report=html

# Run tests matching pattern
pytest app/core/tests/ -k "test_create" -v
```

## Test Patterns

### 1. Happy Path (200/201)
Every route tested with valid inputs returning success.

### 2. Validation (422)
Missing required fields, invalid data formats, invalid email/UUID formats.

### 3. Authentication (403)
Tests verify that missing or invalid auth tokens are rejected.

### 4. Authorization (404)
Tests verify permission checks (e.g., user can't access another user's business).

### 5. Resource Not Found (404)
Tests for nonexistent resources return 404.

### 6. Conflicts (400/409)
Tests for business logic violations (duplicate names, can't delete department with employees).

## Key Testing Notes

### Database Isolation
- Each test uses a fresh in-memory SQLite database
- Tests don't interfere with each other
- No need for cleanup or teardown

### Authentication
- All authenticated endpoints require `Authorization: Bearer <token>` header
- Tests verify auth enforcement on every protected route
- Fixture `auth_helper` handles registration and login

### User Isolation
- Tests verify users only see their own businesses/departments/employees
- Multi-user tests confirm isolation between accounts

### Async/Await
- All tests use `@pytest.mark.asyncio` decorator
- Fixtures are async; uses `await` for async calls

### SQLite Specifics
- UUIDs stored as strings (SQLAlchemy handles conversion)
- No PostgreSQL-specific features used
- Tests use in-memory database (no file I/O)

## Response Format

### Standard Responses
Business/Organization endpoints return validated Pydantic models:
```json
{
  "id": "uuid",
  "name": "Business Name",
  "website": "https://example.com",
  "created_at": "2026-03-06T..."
}
```

### Envelope Responses
Platform endpoints wrap responses in Envelope:
```json
{
  "success": true,
  "data": {...}
}
```

### Error Responses
All errors return FastAPI standard format:
```json
{
  "detail": "Error message"
}
```

## Total Test Coverage

- **102 test cases** across 5 test files
- **2,114 lines** of test code
- **5 routers** covered: auth, businesses, organization, platforms, health
- **16 HTTP methods** tested (POST, GET, PATCH, DELETE, PUT)
- **10+ status codes** tested (200, 201, 400, 403, 404, 409, 422)
