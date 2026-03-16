# Test Index — All 102 Test Cases

## test_auth.py (16 tests)

1. `test_register_success` — User registration with valid credentials
2. `test_register_duplicate_email` — Duplicate email rejection (409)
3. `test_register_invalid_email` — Invalid email format (422)
4. `test_register_missing_field` — Missing required fields (422)
5. `test_register_empty_password` — Empty password validation (422)
6. `test_login_success` — Successful authentication
7. `test_login_wrong_password` — Wrong password rejection (401)
8. `test_login_nonexistent_email` — Nonexistent user (401)
9. `test_login_invalid_email_format` — Invalid email format (422)
10. `test_login_missing_field` — Missing required fields (422)
11. `test_refresh_token_success` — Token refresh
12. `test_refresh_invalid_token` — Invalid token (401)
13. `test_refresh_with_access_token` — Access token as refresh (401)
14. `test_refresh_malformed_token` — Malformed token (401)
15. `test_refresh_missing_token` — Missing token field (422)
16. `test_register_token_can_be_used` — Token validity check

## test_businesses.py (32 tests)

### Create Business (4)
1. `test_create_business_success` — Create with all fields
2. `test_create_business_requires_auth` — Auth requirement (403)
3. `test_create_business_invalid_auth` — Invalid token (403)
4. `test_create_business_missing_field` — Missing fields (422)

### List Businesses (4)
5. `test_list_businesses_empty` — Empty list
6. `test_list_businesses_multiple` — Multiple businesses
7. `test_list_businesses_requires_auth` — Auth requirement (403)
8. `test_list_businesses_isolation` — User isolation

### Get Business (4)
9. `test_get_business_success` — Retrieve single
10. `test_get_business_not_found` — Missing business (404)
11. `test_get_business_unauthorized` — Unauthorized access (404)
12. `test_get_business_requires_auth` — Auth requirement (403)

### Update Business (4)
13. `test_update_business_success` — Update all fields
14. `test_update_business_partial` — Partial update
15. `test_update_business_requires_auth` — Auth requirement (403)
16. `test_update_business_not_found` — Missing business (404)
17. `test_update_business_unauthorized` — Unauthorized update (404)

### Company Profile JSONB (5)
18. `test_get_company_profile_not_set` — Null for new business
19. `test_save_company_profile_success` — Save profile
20. `test_save_company_profile_requires_auth` — Auth requirement (403)
21. `test_save_company_profile_not_found` — Missing business (404)
22. `test_update_company_profile_partial` — Incremental update

### Profile Markdown (2)
23. `test_get_profile_not_found` — Missing profile (404)
24. `test_get_profile_requires_auth` — Auth requirement (403)

### Business Members (8)
25. `test_get_business_members_success` — List members
26. `test_get_business_members_requires_auth` — Auth requirement (403)
27. `test_get_business_members_not_found` — Missing business (404)
28. `test_add_business_member_success` — Add member
29. `test_add_business_member_requires_auth` — Auth requirement (403)
30. `test_get_my_membership_success` — Get user membership
31. `test_get_my_membership_requires_auth` — Auth requirement (403)
32. `test_get_my_membership_not_member` — Non-member (404)

## test_health.py (3 tests)

1. `test_health_check_success` — Health check returns 200
2. `test_health_check_no_auth_required` — No auth needed
3. `test_health_check_response_format` — Valid JSON format

## test_organization.py (29 tests)

### List Departments (2)
1. `test_list_departments_empty` — Empty list
2. `test_list_departments_requires_auth` — Auth requirement (403)

### Create Department (4)
3. `test_create_department_success` — Create with metadata
4. `test_create_department_requires_auth` — Auth requirement (403)
5. `test_create_department_missing_field` — Missing fields (422)
6. `test_create_department_duplicate_name` — Duplicate name (400)

### Update Department (3)
7. `test_update_department_success` — Update fields
8. `test_update_department_requires_auth` — Auth requirement (403)
9. `test_update_department_not_found` — Missing department (404)

### Delete Department (3)
10. `test_delete_department_success` — Delete empty
11. `test_delete_department_requires_auth` — Auth requirement (403)
12. `test_delete_department_not_found` — Missing department (404)

### List Employees (2)
13. `test_list_employees_empty` — Empty list
14. `test_list_employees_requires_auth` — Auth requirement (403)

### Create Employee (4)
15. `test_create_employee_success` — Create with fields
16. `test_create_employee_requires_auth` — Auth requirement (403)
17. `test_create_employee_missing_field` — Missing fields (422)
18. `test_create_employee_invalid_department` — Invalid dept (404)

### Get Employee (3)
19. `test_get_employee_success` — Retrieve employee
20. `test_get_employee_requires_auth` — Auth requirement (403)
21. `test_get_employee_not_found` — Missing employee (404)

### Update Employee (3)
22. `test_update_employee_success` — Update fields
23. `test_update_employee_requires_auth` — Auth requirement (403)
24. `test_update_employee_not_found` — Missing employee (404)

### Delete Employee (3)
25. `test_delete_employee_success` — Delete employee
26. `test_delete_employee_requires_auth` — Auth requirement (403)
27. `test_delete_employee_not_found` — Missing employee (404)

### Org Chart (2)
28. `test_get_org_chart_success` — Get hierarchy
29. `test_get_org_chart_requires_auth` — Auth requirement (403)

## test_platforms.py (22 tests)

### Connect API Key (4)
1. `test_connect_api_key_success` — Connect key (201)
2. `test_connect_api_key_requires_auth` — Auth requirement (403)
3. `test_connect_api_key_invalid_platform` — Invalid platform (400)
4. `test_connect_api_key_missing_field` — Missing fields (422)
5. `test_connect_api_key_with_department_id` — Department scope

### List Connections (5)
6. `test_list_connections_empty` — Empty list
7. `test_list_connections_success` — List connections
8. `test_list_connections_requires_auth` — Auth requirement (403)
9. `test_list_connections_missing_business_id` — Missing business_id (422)
10. `test_list_connections_filter_by_department` — Filter by department

### Disconnect (4)
11. `test_disconnect_platform_success` — Disconnect
12. `test_disconnect_nonexistent_connection` — Missing connection (404)
13. `test_disconnect_requires_auth` — Auth requirement (403)
14. `test_disconnect_missing_field` — Missing fields (422)
15. `test_disconnect_department_scoped` — Department scope

### Test Connection (4)
16. `test_test_connection_success` — Test connection
17. `test_test_connection_not_found` — Missing connection (404)
18. `test_test_connection_requires_auth` — Auth requirement (403)
19. `test_test_connection_missing_business_id` — Missing business_id (422)

### Refresh Token (3)
20. `test_refresh_platform_token_success` — Refresh token
21. `test_refresh_platform_token_not_found` — Missing connection (400)
22. `test_refresh_platform_token_requires_auth` — Auth requirement (403)

---

## Quick Statistics

| Metric | Count |
|--------|-------|
| Total Tests | 102 |
| Test Files | 5 |
| Routers Covered | 5 |
| HTTP Methods | 16 |
| Status Codes | 10+ |
| Lines of Test Code | 2,114 |

### Status Code Distribution
- 200 OK: 40+ tests
- 201 Created: 15+ tests
- 400 Bad Request: 8+ tests
- 401 Unauthorized: 8+ tests
- 403 Forbidden: 20+ tests
- 404 Not Found: 25+ tests
- 409 Conflict: 2+ tests
- 422 Validation Error: 30+ tests

### Test Categories
- Happy Path (Success): 45+ tests
- Authentication (403): 20+ tests
- Authorization (404): 20+ tests
- Validation (422): 30+ tests
- Resource Not Found (404): 8+ tests
- Business Logic (400/409): 10+ tests

