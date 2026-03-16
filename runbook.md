# Workforce Runbook

> Technical reference — database schema, platform architecture, and system documentation
> March 2026

---

## 1. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui | Department-dynamic tab SPA with dark mode |
| State | Zustand + TanStack React Query | UI state + server cache |
| Backend | FastAPI + SQLAlchemy (async) + Pydantic v2 | REST API (23 routers, 23 mounts) |
| Database | PostgreSQL (20 tables, fully relational) | Queryable state with proper dimensional FKs |
| AI | Claude CLI (12 employee system prompts) | Per-business CLI tokens, department-scoped |
| Auth | JWT (HS256) + bcrypt + AES-256-GCM | User auth + credential encryption |
| OAuth | OAuth2 Authorization Code + PKCE | Platform integrations (department-scoped) |
| Terminal | xterm.js + WebSocket + PTY | Embedded CLI setup flow |
| Scheduling | APScheduler (AsyncIOScheduler + CronTrigger) | Recurring tasks (Twilio sync) |
| Real-time | Server-Sent Events (SSE) | Live call streaming |
| Deployment | Docker + docker-compose | Containerized deployment |

---

## 2. Database Schema

PostgreSQL 17 hosted on Supabase. **20 tables** across model files organized into **Dimension Tables** (entities), **Fact Tables** (events and transactions), **Platform Tables** (conversation data), **Content Tables** (media and posts), and **Automation Tables** (workflows). All tables use UUID primary keys. Business-scoped data is isolated via `business_id` foreign keys. Schema changes applied directly via Supabase SQL Editor or `apply_migration`.

**Note:** `org_templates` exists in DB but has no SQLAlchemy model (legacy table, not actively used).

### Table Summary

#### Dimension Tables (Entities)

| Table | Model File | Purpose | Columns |
|-------|-----------|---------|---------|
| users | core/models/user.py | Authentication identity | 6 |
| businesses | core/models/business.py | Business metadata + profile | 16 |
| business_members | core/models/business.py | Multi-tenant membership + permissions | 7 |
| departments | core/models/organization.py | AI workforce departments + call routing + SMS/WhatsApp | 14 |
| employees | core/models/organization.py | AI employees with system prompts | 15 |
| contacts | marketing/models.py | CRM contacts/prospects — single table for full lifecycle | 31 |

#### Fact Tables (Events & Transactions)

| Table | Model File | Purpose | Columns |
|-------|-----------|---------|---------|
| interactions | marketing/models.py | Contact touchpoints (calls, emails, etc.) | 10 |
| business_phone_lines | marketing/models.py | Business phone lines (mainline, tracking, department) → campaign attribution | 14 |
| jobs | operations/models.py | Jobs/projects linked to customers | 15 |
| payments | finance/models.py | Payment records + Stripe integration | 19 |

#### Platform Tables (Conversations, etc.)

| Table | Model File | Purpose | Columns |
|-------|-----------|---------|---------|
| connected_accounts | core/models/connected_account.py | Encrypted platform credentials | 12 |
| conversations | core/models/conversation.py | Chat threads with department heads | 13 |
| conversation_messages | core/models/conversation.py | Individual messages | 8 |
| notifications | core/models/notification.py | In-app alerts | 12 |
| phone_settings | admin/models.py | Per-business phone + A2P configuration | 25 |

#### Content Tables (Media & Posts)

| Table | Model File | Purpose | Columns |
|-------|-----------|---------|---------|
| media_files | marketing/models.py | Uploaded images for content posts | 8 |
| content_posts | marketing/models.py | Content drafts and published social posts | 11 |

#### Automation Tables (Workflows)

| Table | Model File | Purpose | Columns |
|-------|-----------|---------|---------|
| workflows | *(no model — DB only)* | Reusable workflow definitions | 12 |
| workflow_runs | *(no model — DB only)* | Individual workflow execution runs | 14 |

**Note:** `workflows` and `workflow_runs` exist in DB but have no SQLAlchemy models yet. Conversations and notifications reference them via `workflow_id` / `run_id` FKs.

---

### DIMENSION TABLES

#### Auth & Multi-Tenancy

##### users (6 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| email | VARCHAR UNIQUE | Login email |
| password_hash | VARCHAR | bcrypt hashed password |
| full_name | VARCHAR | Display name |
| created_at | TIMESTAMPTZ | Registration timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

##### businesses (16 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| name | VARCHAR | Business name |
| website | VARCHAR(500) | Business website URL |
| industry | VARCHAR(100) | Industry category |
| plan | VARCHAR(20) | Subscription plan (free, pro, agency) |
| description | TEXT | Business description |
| services | TEXT | Services offered |
| target_audience | TEXT | Target audience |
| online_presence | TEXT | Website, social handles, Google listing |
| brand_voice | TEXT | Brand tone and voice |
| goals | TEXT | Business goals |
| competitive_landscape | TEXT | Key competitors |
| profile_source | VARCHAR(50) | How profile was built (e.g., "elena_research") |
| created_by | UUID FK → users | User who created |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

##### business_members (7 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Which business |
| user_id | UUID FK → users | Which user |
| invited_by | UUID FK → users | Who invited this member (nullable) |
| joined_at | TIMESTAMPTZ | Join timestamp |
| is_owner | BOOLEAN | Owner flag (bypasses tab restrictions) |
| allowed_tabs | JSONB | Array of tab paths member can access (NULL = all) |

**Unique constraint:** `(business_id, user_id)`

---

#### Organization

##### departments (14 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | NULL = system/template, UUID = business-scoped |
| name | VARCHAR(100) | Department name |
| description | TEXT | What this department does |
| documentation | TEXT | Full department reference doc (markdown) |
| icon | VARCHAR(50) | Lucide icon name |
| display_order | INTEGER | Tab ordering in UI |
| forward_number | VARCHAR(20) | Personal phone to forward inbound calls to (E.164) |
| enabled | BOOLEAN | Whether this department accepts call routing (default: true) |
| sms_enabled | BOOLEAN | Send SMS notification (caller name + reason) to forward_number (default: false) |
| whatsapp_enabled | BOOLEAN | WhatsApp notifications enabled (default: false) |
| whatsapp_sender_sid | TEXT | Twilio WhatsApp sender SID |
| whatsapp_sender_status | TEXT | WhatsApp sender registration status (default: 'none') |
| created_at | TIMESTAMPTZ | Creation timestamp |

##### employees (15 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | NULL = system/template, UUID = business-scoped |
| department_id | UUID FK → departments | Which department this employee belongs to |
| name | VARCHAR(100) | Display name |
| title | VARCHAR(200) | Job title |
| file_stem | VARCHAR(200) | Slug ID (e.g., `marcus_director_of_seo`) — used as filename and employee_id |
| model_tier | VARCHAR(20) | opus, sonnet, haiku |
| system_prompt | TEXT | Full system prompt (role, responsibilities, Claude instructions) |
| reports_to | UUID FK → employees | Direct supervisor UUID (self-referencing) |
| status | VARCHAR(20) | active, inactive |
| capabilities | JSONB | Structured metadata |
| job_skills | TEXT | High-level skills summary |
| is_head | BOOLEAN | True for department heads (CMO, COO, etc.) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

**Unique constraint:** `(business_id, file_stem)`

---

#### Customer Dimension

##### contacts (31 columns)

Single table for the full customer lifecycle: prospect → lead → active_customer. No separate prospects or customers table.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this contact belongs to |
| full_name | VARCHAR | Contact name |
| company_name | VARCHAR | Company/organization name |
| phone | VARCHAR | Primary phone (indexed) |
| phone_verified | BOOLEAN | Phone verification status |
| email | VARCHAR | Email address (indexed) |
| email_verified | BOOLEAN | Email verification status |
| status | VARCHAR(30) | new, prospect, lead, active_customer, no_conversion, other (default: new) |
| source_channel | VARCHAR | How they first interacted (call, form, email, sms, walk_in) |
| campaign_id | VARCHAR | Campaign that sourced them (string, not FK) |
| utm_source | VARCHAR | UTM source |
| utm_medium | VARCHAR | UTM medium |
| utm_campaign | VARCHAR | UTM campaign |
| stripe_customer_id | VARCHAR | Stripe customer ID (for billing sync) |
| customer_type | VARCHAR | new, returning |
| first_contact_date | TIMESTAMPTZ | First interaction timestamp |
| first_invoice_date | TIMESTAMPTZ | First invoice timestamp |
| acquisition_campaign | VARCHAR | Campaign that converted them |
| acquisition_channel | VARCHAR | Channel that converted them |
| revenue_since_contact | NUMERIC | Total revenue from this contact |
| last_transaction_date | TIMESTAMPTZ | Most recent payment |
| touchpoint_count | INTEGER | Total interactions |
| address_line1 | VARCHAR | Street address |
| city | VARCHAR | City |
| state | VARCHAR | State/province |
| zip_code | VARCHAR | Zip/postal code |
| country | VARCHAR | Country |
| notes | TEXT | Internal notes |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

---

### FACT TABLES

##### interactions (10 columns)

Contact touchpoints — calls, emails, SMS, notes. Lean table with metadata JSONB for flexible per-type data.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this interaction belongs to |
| contact_id | UUID FK → contacts | Who this interaction involves |
| type | VARCHAR(30) | call, email, sms, form_submit, note |
| direction | VARCHAR(20) | inbound, outbound |
| subject | VARCHAR(500) | Message subject |
| body | TEXT | Full message/transcript |
| metadata | JSONB | call_sid, recording_url, duration_seconds, transcript, summary, etc. |
| created_by | UUID | User or system that created this |
| created_at | TIMESTAMPTZ | When this interaction occurred |

**Note:** Python attribute is `metadata_` (SQLAlchemy reserved word); DB column is `metadata`; Pydantic serializes as `"metadata"`.

##### business_phone_lines (14 columns)

Business phone lines — mainline, tracking, or department lines. Maps Twilio numbers to campaigns for attribution.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this number belongs to |
| department_id | UUID FK → departments | Which department uses this number |
| twilio_number | VARCHAR(20) | E.164 Twilio phone number |
| twilio_number_sid | VARCHAR(100) | Twilio number SID |
| friendly_name | VARCHAR(255) | Human-readable label |
| campaign_name | VARCHAR (nullable) | Campaign name (string attribution) — nullable for mainline |
| ad_account_id | VARCHAR | Ad platform account ID |
| channel | VARCHAR | google_ads, facebook_ads, organic, etc. |
| line_type | VARCHAR(20) | "mainline", "tracking", or "department" |
| active | BOOLEAN | Whether currently routing calls |
| shaken_stir_status | VARCHAR(20) | STIR/SHAKEN attestation level (A, B, C) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

##### jobs (15 columns)

Job/project records linked to customers. Status lifecycle: new → in_progress → completed → billing → billed.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this job belongs to |
| contact_id | UUID FK → contacts | Customer this job is for |
| title | VARCHAR | Job name/title |
| description | TEXT | Detailed job description |
| status | VARCHAR | new, in_progress, completed, billing, billed |
| notes | TEXT | Job notes |
| amount_quoted | NUMERIC(12,2) | Quoted amount |
| amount_billed | NUMERIC(12,2) | Billed amount |
| metadata | JSONB | Custom fields |
| created_by | UUID | User who created |
| started_at | TIMESTAMPTZ | Job start timestamp |
| completed_at | TIMESTAMPTZ | Job completion timestamp |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

**Note:** Python attribute is `metadata_`; DB column is `metadata`.

##### payments (19 columns)

Payment records with first-class Stripe integration columns. Supports one-time and subscription payments.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this payment belongs to |
| contact_id | UUID FK → contacts | Customer who paid |
| job_id | UUID FK → jobs | Job this payment is for |
| amount | NUMERIC(12,2) | Payment amount |
| payment_type | VARCHAR(20) | one_time, subscription |
| frequency | VARCHAR(20) | daily, weekly, monthly, annual (subscriptions only) |
| provider | VARCHAR(50) | stripe, square, cash, check, zelle, venmo |
| source | VARCHAR(50) | stripe_sync, manual_upload, manual_entry, quickbooks_import |
| interaction_id | UUID FK → interactions | Call/interaction that drove this payment |
| status | VARCHAR(20) | pending, completed, failed, refunded (default: completed) |
| stripe_customer_id | VARCHAR(255) | cus_xxx — Stripe customer (indexed) |
| stripe_invoice_id | VARCHAR(255) | in_xxx — one-time invoice (indexed) |
| stripe_subscription_id | VARCHAR(255) | sub_xxx — recurring subscription (indexed) |
| stripe_payment_intent_id | VARCHAR(255) | pi_xxx — the actual charge (indexed) |
| billing_ref | JSONB | Overflow for non-Stripe providers (QuickBooks, Square) |
| notes | TEXT | Payment notes |
| paid_at | TIMESTAMPTZ | Payment timestamp |
| created_at | TIMESTAMPTZ | Creation timestamp |

---

### PLATFORM TABLES

##### connected_accounts (12 columns)

Encrypted credentials for platform integrations. Department-scoped (Stripe → Billing, Facebook → Marketing).

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Which business owns this connection |
| department_id | UUID FK → departments | Which department uses this (NULL = shared/business-wide) |
| platform | VARCHAR(50) | facebook, google_ads, claude, twilio, stripe, etc. |
| auth_method | VARCHAR(20) | oauth, api_key, cli |
| encrypted_credentials | BYTEA | AES-256-GCM encrypted tokens |
| scopes | VARCHAR(1000) | OAuth scopes |
| external_account_id | VARCHAR(255) | Platform account/user ID |
| token_expires_at | TIMESTAMPTZ | For refresh scheduling |
| status | VARCHAR(20) | active, expired, revoked |
| connected_at | TIMESTAMPTZ | Connection timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

**Unique constraint:** `(business_id, platform, department_id)`

##### conversations (13 columns)

Chat threads — user chat with department heads, or workflow-driven conversations.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this conversation belongs to |
| user_id | UUID FK → users | User in conversation |
| title | VARCHAR(255) | Conversation title (auto-generated) |
| status | VARCHAR(20) | active, archived, approved |
| workflow_id | UUID FK → workflows | Linked workflow (nullable) |
| run_id | UUID FK → workflow_runs | Linked workflow run (nullable) |
| employee_id | UUID FK → employees | Which employee is the assistant |
| source | VARCHAR(20) | user_chat, department_chat |
| is_read | BOOLEAN | Read status (drives notification badge) |
| message_count | INTEGER | Message count |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

##### conversation_messages (8 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| conversation_id | UUID FK → conversations | Which conversation |
| role | VARCHAR(20) | user, assistant |
| content | TEXT | Message text (markdown) |
| proposal | JSONB | Structured proposal data (nullable) |
| delivery_content | JSONB | Delivery content (nullable) |
| status | VARCHAR(20) | complete, error |
| created_at | TIMESTAMPTZ | Send timestamp |

##### notifications (12 columns)

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this notification belongs to |
| user_id | UUID FK → users | User this notification is for |
| type | VARCHAR(50) | info, error, new_call, call_completed, etc. |
| title | VARCHAR(255) | Notification title |
| message | TEXT | Notification body |
| workflow_id | UUID FK → workflows | Linked workflow (nullable) |
| run_id | UUID FK → workflow_runs | Linked workflow run (nullable) |
| is_read | BOOLEAN | Read status |
| read_at | TIMESTAMPTZ | When read |
| metadata | JSONB | Extra data (Python attr: metadata_) |
| created_at | TIMESTAMPTZ | Creation timestamp |

##### phone_settings (25 columns)

Per-business Twilio phone + A2P configuration. One row per business. A2P 10DLC registration is done in Twilio Console; only the SIDs are stored here for querying campaign status via API.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this config belongs to (UNIQUE) |
| greeting_text | TEXT | Initial greeting played to callers |
| voice_name | VARCHAR(100) | TTS voice (default: Google.en-US-Chirp3-HD-Aoede) |
| hold_message | TEXT | Message played after caller states reason |
| recording_enabled | BOOLEAN | Whether calls are recorded (default: true) |
| transcription_enabled | BOOLEAN | Whether transcripts are generated (default: false) |
| forward_all_calls | BOOLEAN | Skip IVR, forward straight to default number (default: true) |
| default_forward_number | VARCHAR(20) | Fallback forward number |
| ring_timeout_s | INTEGER | Seconds to ring before timeout (default: 30) |
| business_hours_start | TIME | When business hours begin (e.g. 09:00) |
| business_hours_end | TIME | When business hours end (e.g. 17:00) |
| business_timezone | VARCHAR(50) | IANA timezone for business hours (default: America/Chicago) |
| after_hours_enabled | BOOLEAN | Whether after-hours mode is active (default: false) |
| after_hours_message | TEXT | Message played during after-hours |
| after_hours_action | VARCHAR(20) | After-hours handling: "message" or "forward" (default: message) |
| after_hours_forward_number | VARCHAR(20) | Phone number to forward to during after-hours |
| messaging_service_sid | VARCHAR(50) | Twilio Messaging Service SID (for A2P campaign status checks + adding numbers) |
| brand_registration_sid | VARCHAR(50) | TCR brand registration SID (for verifying numbers are branded) |
| sms_enabled | BOOLEAN | Global SMS toggle (default: false) |
| whatsapp_enabled | BOOLEAN | Global WhatsApp toggle (default: false) |
| whatsapp_from_number | VARCHAR(20) | WhatsApp sender number |
| webhook_base_url | VARCHAR(500) | Public URL for Twilio webhooks (e.g., https://api.example.com) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

Department-level call routing is handled by `departments.forward_number`, `departments.enabled`, and `departments.sms_enabled`.

---

### CONTENT TABLES

##### media_files (8 columns)

Uploaded images for content posts. Files stored on disk at `businesses/{biz_id}/media/{uuid}.{ext}`.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this file belongs to |
| filename | VARCHAR(255) | Original filename |
| file_path | VARCHAR(500) | Relative path on disk |
| mime_type | VARCHAR(50) | image/jpeg, image/png, image/gif, image/webp |
| size_bytes | INTEGER | File size in bytes |
| uploaded_by | UUID | User who uploaded |
| created_at | TIMESTAMPTZ | Upload timestamp |

##### content_posts (11 columns)

Content drafts and published posts for social media platforms.

| Column | Type | Purpose |
|--------|------|---------|
| id | UUID PK | Primary key |
| business_id | UUID FK → businesses | Business this post belongs to |
| content | TEXT | Post body text |
| platform_targets | JSONB | Array of platform names (e.g. ["facebook", "instagram"]) |
| media_ids | JSONB | Array of media_file UUIDs attached to this post |
| status | VARCHAR(20) | draft, posted, failed |
| posted_at | TIMESTAMPTZ | When the post was published (nullable) |
| posted_by | UUID FK → employees | Which employee executed the post (nullable) |
| platform_results | JSONB | Per-platform outcome data (nullable) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |

---

### KEY CONSTRAINTS

#### Foreign Key Rules

- **Business isolation:** All business-scoped tables have `business_id` FK
- **Contact linking:** `jobs.contact_id`, `payments.contact_id`, `interactions.contact_id` all FK → contacts
- **Job → Payment chain:** `payments.job_id` FK → jobs (links payment to the work billed for)
- **Call attribution chain:** business_phone_line → call (interaction) → contact → lead (opportunity) → job → payment, linked via business_phone_lines.campaign_name and contact_id/job_id FKs

#### Unique Constraints

- `users(email)` — Email is unique across all users
- `business_members(business_id, user_id)` — One membership per user per business
- `employees(business_id, file_stem)` — Unique employee slug per business
- `departments(business_id, name)` — Unique department name per business
- `connected_accounts(business_id, platform, department_id)` — Can connect same platform to different departments
- `phone_settings(business_id)` — One phone config per business

#### System vs. Business-Scoped Rows

- `business_id=NULL` → System/template row (departments, employees only)
- `business_id=UUID` → Business-scoped copy (live business data)

---

### SQLAlchemy & Pydantic Notes

- **Metadata naming:** `Interaction.metadata_`, `Job.metadata_`, `Notification.metadata_` are Python attributes; DB column is `metadata`; Pydantic serializes as `"metadata"` in JSON
- **UUID generation:** All PK columns auto-generate UUID v4 on insert
- **Timestamps:** `created_at` set on insert, `updated_at` updated on every change (both TIMESTAMPTZ)

---

## 3. Data Flow Across Departments

```
Marketing creates Campaign
    ↓
Campaign gets Business Phone Lines (phones assigned with campaign_name string)
    ↓
Customer calls phone line → Interaction (call, campaign attribution via business_phone_lines.campaign_name, department_id)
    ↓ (IVR routes to Sales)
Sales creates Opportunity (linked to campaign, contact, call)
    ↓ (contextual chat within Sales workspace)
    ↓ (deal won)
Operations creates Job (linked to opportunity, contact, department_id)
    ↓ (contextual chat within Operations workspace)
    ↓ (job completed)
Billing creates Payment (linked to job, opportunity, contact, department_id)
    ↓
Notification: payment_received (in Billing department)

```

---

## 4. Authentication & Security

### User Auth (JWT)

JWT-based with HS256 signing. 30-minute access tokens, 7-day refresh tokens.

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | /auth/register | Create user + return JWT pair |
| POST | /auth/login | Verify bcrypt hash + return JWT pair |
| POST | /auth/refresh | Refresh expired access token |

All protected endpoints use `get_current_user_id` dependency from Authorization header.

### Team Authorization

Tab-based access control via `business_members.allowed_tabs` (JSONB array). `is_owner: bool` flag identifies business owner. Non-owners see only permitted tabs.

### Encryption

All OAuth tokens, CLI tokens, and API keys encrypted at rest with AES-256-GCM (32-byte key from `ENCRYPTION_KEY` env var, base64-encoded). Each value includes unique nonce + auth tag. Service: `encryption_service.py`.

---

## 5. Employee System

### Model Tiers

| Tier | Model | Use Case |
|------|-------|----------|
| Opus | claude-opus-4-6 | Owner / CEO + IT Director (Christian, Casey) |
| Sonnet | claude-sonnet-4-6 | Department heads + senior specialists (Elena, Marcus, Luna, Jordan, Riley, Dana, Ivy) |
| Haiku | claude-haiku-4-5-20251001 | Specialist execution, high-throughput tasks (Alex, Morgan, Quinn, Grace) |

### System Prompt Loading

1. `claude_cli_service.py` reads `system_prompt` from DB (`employees.system_prompt` column)
2. Each employee row contains the full system prompt with role description, responsibilities, and Claude-specific instructions
3. Self-documentation endpoint: `POST /api/v1/tools/self-document` lets employees update their own `system_prompt` in DB

### Platform Employees (9 Workers)

Workers get `--tools Bash,WebSearch,WebFetch` and `--dangerously-skip-permissions`. They discover connected platforms via `GET /tools/available`, research API docs via WebSearch, and route requests through `POST /tools/proxy`.

| Department | Platform Employees |
|-----------|-------------------|
| Marketing | Marcus, Luna, Alex |
| Sales | Riley |
| Operations | Morgan |
| IT | Casey |
| Administration | Ivy, Grace |
| Billing | Quinn |

Directors (Elena, Jordan, Dana) delegate to specialist employees rather than executing platform actions directly. Casey (IT) is both director and platform employee — Opus tier with full tool access for master actions.

### Internal Tools API

| Method | Path | Purpose |
|--------|------|---------|
| GET | /tools/available | Discover connected platforms |
| POST | /tools/proxy | Generic credential proxy (13 platforms) |
| POST | /tools/twilio/provision | Buy number + create BusinessPhoneLine |
| POST | /tools/twilio/release | Release number + deactivate BusinessPhoneLine |
| POST | /tools/github/push-site | Multi-step git commit via GitHub API (used by IT/Casey for website deployments) |
| POST | /tools/self-document | Employee updates own system_prompt |

Proxy validates URLs against platform-specific allowlists to prevent credential leakage.

---

## 7. IVR & Call Routing

### Inbound Call Flow

```
1. Call arrives at business_phone_line.twilio_number
2. Look up BusinessPhoneLine → campaign_name, line_type, department_id (FK)
3. Look up Department → forward_number, enabled
4. Check after-hours based on phone_settings.business_hours_* and .business_timezone
5. If after-hours:
   a. If after_hours_action='message': Play phone_settings.after_hours_message
   b. If after_hours_action='forward': Forward to phone_settings.after_hours_forward_number
   c. Tag interaction metadata as "After Hours" or "After Hours Forward"
6. If in-hours:
   a. Find or create Contact from caller ID
   b. Play greeting from phone_settings.greeting_text
   c. <Gather input="speech"> collects caller name + reason
   d. Ivy (Haiku) normalizes transcript → AI routes to best department
7. Forward to department.forward_number with recording (or skip if after-hours forward)
8. Tag interaction metadata as "Direct Forward" if forwarded to department
9. Create Interaction with: department_id, campaign_name (from business_phone_lines), contact_id
```

### Outbound Call Flow

```
1. User in dept tab clicks "Call" on contact/opportunity
2. Look up BusinessPhoneLine linked to department (via department_id FK)
3. Place call with callerId = business_phone_line.twilio_number
4. Create Interaction with: department_id, contact_id, opportunity_id (if in deal context)
```

### Post-Call Analysis

CallAnalysisService enriches Interaction after transcription:
- Determines/confirms `department_id`, `employee_id`
- Sets `call_category` (inquiry, job_request, payment_inquiry, complaint, etc.)
- Sets `suggested_action` for department handling
- Call appears in relevant department's call panel

### Phone Configuration

**Business-level config** in `phone_settings`: greeting_text, voice_name, recording_enabled, transcription_enabled, forward_all_calls, ring_timeout, business_hours, after_hours settings (message + action + forward number), hold_message, webhook_base_url.

**Department-level routing** on `departments` table: forward_number, enabled, sms_enabled. Phone numbers are on `business_phone_lines` table (linked via `department_id` FK).

**Twilio Webhooks:** webhook_base_url is stored in `phone_settings` table (DB source of truth, not .env). Supports after-hours with two modes: "message" (plays after-hours message + hangs up) and "forward" (forwards to after_hours_forward_number).

---

## 8. Notification System

### CRM Notifications

| Event | Type | Scope |
|-------|------|-------|
| Inbound call | new_call | department_id from business_phone_lines |
| Call analyzed | call_completed | department_id on Interaction |
| Deal created | opportunity_created | Sales department |
| Deal stage changed | opportunity_stage_changed | Sales department |
| Payment received | payment_received | Billing department |
| Job completed | job_completed | Operations department |
| Job overdue | job_overdue | Operations department |

**API:** `GET /notifications` (list + unread count), `POST /notifications/read` (mark one), `POST /notifications/read-all`.

---

## 9. Onboarding (3-Step Setup)

Setup banner guides new businesses through a streamlined onboarding:

1. **Connect Claude** — Embedded xterm.js terminal runs `claude setup-token` OAuth flow. Token captured from PTY output, ANSI-stripped, encrypted, stored per-business in `connected_accounts` with `platform='claude'`.

2. **Build Company Profile (Elena-Led)** — User provides basic seed info (business name + phone + website or social link). Elena (CMO, Marketing) researches the business online via WebSearch/WebFetch — finds website content, social profiles, Google Business listing, reviews, competitors. Elena asks a few clarifying questions (services offered, target audience, key differentiators). Output saved to dedicated columns on `businesses` table (`description`, `services`, `target_audience`, `online_presence`, `brand_voice`, `goals`, `competitive_landscape`, `profile_source`). This profile is injected into every employee's context when they run, so all departments share the same baseline business knowledge without re-asking.

The 13-person workforce (across 6 departments) is automatically provisioned on business creation. After setup, user clicks into any department tab to start working with that team.

---

## 10. Platform Connections (Department-Scoped)

Integrations stored in `connected_accounts` with `department_id` FK. Each integration maps to a department.

| Platform | Department | Employees Unlocked |
|----------|-----------|-------------------|
| Claude CLI | All (NULL dept) | All employees |
| Stripe | Billing | Quinn |
| Facebook/Instagram | Marketing | Luna, Alex |
| Google (Analytics, Ads, Business) | Marketing | Marcus, Alex |
| LinkedIn | Marketing | Luna |
| TikTok | Marketing | Luna, Alex |
| Twilio | Shared (NULL dept) | Ivy, Jordan |

**On-demand auth:** Employee needs platform → check `(business_id, platform)` → if missing, notify user → user connects on Connections page.

**Connection → Profile sync:** When a new platform connection is added (via Connections page or on-demand auth), relevant metadata is saved to the `online_presence` column on the `businesses` table. This keeps the business profile as the single source of truth for what the business has connected. Employees referencing the profile always know which platforms are available without querying `connected_accounts` separately.

**CLI token expiry:** `claude_cli_service.py` monitors stderr for 401/token errors → marks `connected_accounts.status='expired'` → frontend shows reconnect banner.

---

## 11. Inline Delegation (Chat)

Department heads delegate to specialist employees via `json:delegate` blocks in chat. Backend detects block → calls specialist via `call_employee_inline()` → specialist executes (with Bash+curl if platform employee) → results appended to department head's response.

---

## 12. Contextual Conversations

Conversations are embedded on entities, not standalone:

| Entity | Department | conversation_type |
|--------|-----------|------------------|
| Opportunity | Sales | entity_chat |
| Job | Operations | entity_chat |
| Contact | Any | entity_chat |
| Campaign | Marketing | entity_chat |

Each conversation saves with: `department_id`, `contact_id`, `opportunity_id` or `job_id`, `campaign_id` as applicable.

Other conversation types: `department_chat` (direct chat with department head).

---

## 13. Frontend Architecture

### Tab Layout (7 Tabs)

Marketing, Sales, Operations, Billing, IT, Admin, Reports.

### State Management

**Zustand:** Auth, business selection, department selection, setup flow, theme (light/dark/system).

**React Query:** Server cache for all business data. Queries filtered by `department_id` for workspace isolation.

### Key Components

| Component | Purpose |
|-----------|---------|
| AppShell | Main layout with topbar + 8-tab navigation |
| SetupBanner | 3-step onboarding |
| DepartmentChat | Department head chat + conversation sidebar |
| DepartmentCallsPanel | Reusable call panel per department |
| EntityChat | Contextual chat on entities |
| MarkdownMessage | AI response renderer |
| useRunMonitor | SSE + polling fallback for live monitoring |

### Workforce Tab

Organization structure displayed as department hierarchy cards with:
- Department name with color coding
- Collapsible employee list with names
- Job descriptions expandable per employee
- Model tier displayed (Opus, Sonnet, Haiku)
- No templates — all departments configured at setup

---

## 14. Deployment

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| DATABASE_URL | Yes | PostgreSQL connection string |
| SECRET_KEY | Yes | General encryption |
| JWT_SECRET_KEY | Yes | JWT signing |
| ENCRYPTION_KEY | Yes | AES-256-GCM (base64-encoded 32-byte) |
| CORS_ORIGINS | No | Allowed frontend origins |
| GOOGLE_CLIENT_ID/SECRET | For OAuth | Google integrations |
| META_APP_ID/SECRET | For OAuth | Facebook/Instagram |
| SENDGRID_API_KEY | For Email | Email delivery |

### Azure Deployment

**Backend:** FastAPI in Docker on Azure Container Apps. Enable SSE + WebSocket support. Single replica recommended for APScheduler.

**Frontend:** React SPA on Azure Static Web Apps. `npm run build` → `dist/`. API proxy rewrites `/api/*` to backend URL. All other routes serve `index.html`.

### Local Development

```bash
cp .env.example .env
make setup              # Create venv and install dependencies
source venv/bin/activate
make server             # Start backend (:8000) — clean terminal, NOT inside Claude Code
cd frontend && npm run dev  # Start frontend (:5173)
```

Twilio webhooks require a public URL (webhook_base_url) configured in the `phone_settings` table per business (typically set up via admin panel). For local development with ngrok: `ngrok http 8000` → save the forwarding URL to `phone_settings.webhook_base_url` for the business.

---

End of Runbook
