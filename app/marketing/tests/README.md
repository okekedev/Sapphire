# Marketing Department Test Suite

Comprehensive pytest tests for the marketing department routers.

## Test Modules

### test_contacts.py
Tests for all contact management endpoints:
- CRM Summary (GET /contacts/summary)
- List Contacts (GET /contacts)
- Create Contact (POST /contacts)
- Get Contact (GET /contacts/{id})
- Update Contact (PATCH /contacts/{id})
- Update Status (PATCH /contacts/{id}/status)
- Delete Contact (DELETE /contacts/{id})
- List Interactions (GET /contacts/{id}/interactions)
- Log Interaction (POST /contacts/{id}/interactions)

**46 test cases** covering:
- Happy path operations
- Authorization checks (401)
- Not found errors (404)
- Validation errors (422)
- Filtering and search
- Pagination
- Cascade deletes
- Metadata handling

### test_tracking.py
Tests for tracking number management endpoints:
- List Tracking Numbers (GET /tracking-numbers)
- Create Tracking Number (POST /tracking-numbers)
- Update Tracking Number (PATCH /tracking-numbers/{id})
- Delete Tracking Number (DELETE /tracking-numbers/{id})

**28 test cases** covering:
- Happy path operations
- Authorization checks (401)
- Not found errors (404)
- Validation errors (422)
- Business isolation
- Channel variations (Google Ads, Facebook Ads, organic, etc.)
- Department assignment
- Full lifecycle tests

## Running Tests

```bash
# Run all marketing tests
pytest app/marketing/tests/ -v

# Run only contacts tests
pytest app/marketing/tests/test_contacts.py -v

# Run only tracking tests
pytest app/marketing/tests/test_tracking.py -v

# Run a specific test
pytest app/marketing/tests/test_contacts.py::test_create_contact_happy_path -v

# Run with coverage report
pytest app/marketing/tests/ --cov=app.marketing --cov-report=html

# Run tests with detailed output
pytest app/marketing/tests/ -vv -s
```

## Test Organization

Each test is organized as:
1. **Arrange** — Set up test data and fixtures
2. **Act** — Make the API request
3. **Assert** — Verify the response

## Key Patterns

### Authentication
All endpoints require Bearer token authentication via `auth_headers` fixture.

```python
response = await client.get(
    f"/api/v1/contacts?business_id={seed_business.id}",
    headers=auth_headers,  # Must include auth
)
```

### Business Isolation
All endpoints use `business_id` as a query parameter to isolate data.

```python
response = await client.post(
    f"/api/v1/contacts?business_id={seed_business.id}",
    headers=auth_headers,
    json={...},
)
```

### Status Codes
- **200/201** — Success (POST returns 201 Created)
- **204** — Delete success (no content)
- **401** — Unauthorized (missing/invalid auth)
- **404** — Not found (resource doesn't exist)
- **422** — Validation error (invalid input)

### Fixtures Available
- `client` — Async FastAPI test client
- `auth_headers` — Bearer token headers
- `seed_user` — Pre-created test user
- `seed_business` — Pre-created business
- `seed_department` — Pre-created department
- `seed_contact` — Pre-created contact
- `db_session` — Database session with auto-rollback

## Contact Statuses
- `prospect` — Potential customer
- `active_customer` — Paying customer
- `churned` — Lost customer

## Interaction Types
- `call` — Phone call (inbound/outbound)
- `email` — Email communication
- `form_submit` — Website form submission
- `sms` — Text message
- `fb_message` — Facebook message
- `payment` — Payment received
- `note` — Internal note

## Tracking Number Channels
- `paid_search` — Google Ads, Bing, etc.
- `social_media` — Facebook, Instagram, etc.
- `organic` — Organic search results
- `direct` — Direct calls
- `direct_mail` — Mail campaigns
- etc.

## Important Notes

1. **SQLite Testing** — Tests use in-memory SQLite; UUIDs are stored as strings
2. **Metadata Handling** — Interaction.metadata_ in Python → "metadata" in JSON
3. **Business Isolation** — Tests verify business_id isolation
4. **Cascade Deletes** — Contact deletion cascades to interactions
5. **Async/Await** — All tests are async; use `@pytest.mark.asyncio`

## Coverage

- **74 total test cases**
- **100% endpoint coverage**
- **All HTTP methods** — GET, POST, PATCH, DELETE
- **All error conditions** — 401, 404, 422
- **Business logic** — Status transitions, filtering, search, pagination

## CI/CD Integration

These tests are designed to run in CI/CD pipelines:

```bash
# Quick sanity check
pytest app/marketing/tests/ -x  # Stop on first failure

# Full test with coverage
pytest app/marketing/tests/ --cov=app.marketing --cov-fail-under=90

# Generate junit XML for CI
pytest app/marketing/tests/ --junit-xml=test-results.xml
```

## Debugging

```bash
# Show print statements in tests
pytest app/marketing/tests/test_contacts.py -s

# Verbose output with test names
pytest app/marketing/tests/test_contacts.py -vv

# Show local variables on failure
pytest app/marketing/tests/ -l

# Drop into pdb on failure
pytest app/marketing/tests/ --pdb

# Run a single test
pytest app/marketing/tests/test_contacts.py::test_create_contact_happy_path -vv
```
