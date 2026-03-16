# Vision Document

> An AI-Powered Digital Agency with Department-Centric Workspaces
> March 2026

## Executive Summary

This is an AI-powered digital agency platform where 13 Claude-powered employees organize into 6 departments that function as collaborative workspaces. Instead of traditional SaaS tooling with complex dashboards and manual processes, users interact directly with department heads — each department tab has its own AI director who handles strategy, delegates to specialist employees, and executes tasks. There is no central orchestrator; the user (Christian, the owner) goes to the department they need and works with that department's head.

The system uses a 20-table relational database where every CRM fact table is department-scoped: jobs in Operations, payments in Billing, content posts in Marketing. Data flows seamlessly across departments (campaign → opportunity → job → payment), with each entity linked by foreign keys. Employee system prompts and department documentation are stored in the database as the single source of truth.

## Core Architecture

### Department Workspaces

Every department is a tab/workspace with its own:
- **Data table** — Sales owns opportunities, Operations owns jobs, Billing owns payments, Marketing owns campaigns
- **Employees** — AI workers assigned to the department
- **Connections** — Department-scoped integrations (Stripe→Billing, Facebook→Marketing, Twilio→shared)
- **Contextual Chat** — Q&A about entities within the department (conversations on opportunities, jobs, payments)
- **Call Panel** — Real-time inbound/outbound calls for the department
- **Notifications** — CRM events (new call, opportunity created, payment received, job completed)

### Goal-Driven Department Interaction

Each department has a distinct interaction pattern that matches how that department actually works. AI employees combine their role expertise with the human's stated goals — no predefined task templates:

- **Marketing:** User sets a goal ("I want leads from Google Ads") → AI discusses strategy, platforms, budgets, schedules → recommends what to set up and why → department team executes campaigns and lead generation
- **Sales:** Goals are per-lead — AI analyzes past call history, interactions, campaign source → generates pitch recommendations, follow-up strategies, qualification insights for *this specific opportunity*
- **Operations:** Documentation-driven — user records calls, uploads photos, adds manual entries → AI helps document jobs, track progress, move to completion → conversations support links and attachments
- **Finance:** Handoff-driven — completed job moves from Operations to Billing → AI helps invoice, track payment, automate reminders → goal is always "get paid for this job"

### Department Chat

- **Contextual Chat = Q&A** — In-page chat about an entity (opportunity, job, contact). Department AI answers questions and saves insights to DB as memory. Supports links, photos, and manual entries. Department employees execute tasks and produce outputs directly from conversation.

### Connections Are Department-Scoped

Integrations map to departments:
- Stripe → Billing department (invoices, subscriptions, customers)
- Facebook/Instagram → Marketing department (campaign posting, media)
- Twilio → Shared (all departments use it for calls/SMS)

## Organization Structure

13 AI employees across 6 departments, all powered by Claude with role-specific system prompts. Christian (CEO & Founder) is the human owner who interacts directly with department heads. Christian and Grace (Receptionist & Call Router) are also employee rows in Administration for system functionality.

**Marketing Department (4)** — Elena (CMO, Sonnet), Marcus (SEO Director, Sonnet), Luna (Social Media Director, Sonnet), Alex (Content Creator & Strategist, Haiku)

**Sales Department (2)** — Jordan (Sales Director, Sonnet), Riley (Sales Coordinator, Sonnet)

**Operations Department (2)** — Dana (Director of Operations, Sonnet), Morgan (Account Manager, Haiku)

**Billing Department (1)** — Quinn (Billing Specialist, Haiku)

**IT Department (1)** — Casey (Director of IT, Opus)

**Administration Department (3)** — Ivy (Director of Administration, Sonnet), Christian (CEO & Founder, Opus), Grace (Receptionist & Call Router, Haiku)

### Model Tiers

| Tier | Model | Use Case | Employees |
|------|-------|----------|-----------|
| Opus | claude-opus-4-6 | Owner / CEO + IT Director | Christian, Casey |
| Sonnet | claude-sonnet-4-6 | Department heads + senior specialists | Elena, Marcus, Luna, Jordan, Riley, Dana, Ivy |
| Haiku | claude-haiku-4-5-20251001 | Specialist execution, high-throughput tasks | Alex, Morgan, Quinn, Grace |

## Technical Architecture

### Tech Stack

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
| Real-time | Server-Sent Events (SSE) | Live call streaming |
| Deployment | Docker + docker-compose | Containerized deployment |

### Database Schema (20 Tables)

**Dimensions (5):** users, businesses, business_members, departments, employees

**CRM (4):** contacts, interactions, business_phone_lines, jobs

**Facts (2):** jobs, payments

**Platform (5):** connected_accounts, conversations, conversation_messages, notifications, phone_settings

**Content (2):** media_files, content_posts

**Legacy (1):** org_templates (no SQLAlchemy model, not actively used)

All fact tables have proper dimensional foreign keys (no JSONB storing relational data). Departments table has phone fields (twilio_number, forward_number). All CRM tables (interactions, jobs, payments) are scoped to departments.

### Employee System Prompts

Employee system prompts are stored in the database (`employees.system_prompt` column). Each employee row contains the full Claude-specific instructions including role description, responsibilities, and task-specific guidance. Business context (company_profile) is injected into all employee prompts as shared context during conversations.

## Frontend Architecture

### Department-Dynamic Tab Layout

| Tab | Route | Workspace |
|-----|-------|-----------|
| Marketing | /marketing | Content Studio, connected accounts, social posting, contextual chat |
| Sales | /sales | Sales opportunities, pipeline, deal management, contextual chat |
| Operations | /operations | Jobs, scheduling, work orders, completion tracking, contextual chat |
| Billing | /billing | Payments, invoices, subscriptions, revenue, contextual chat |
| IT | /it | Chat with Casey (Opus), GitHub/Azure connections, system tools, master actions |
| Admin | /admin | Phone infrastructure, Twilio numbers, IVR config, call routing |
| Reports | /marketing/reports | Pipeline attribution, campaign ROI, department performance |

### Department Workspace Features

Each department tab includes:
- **Primary data table** — Opportunities (Sales), Jobs (Operations), Payments (Billing), Campaigns (Marketing)
- **Secondary data** — Contacts, interactions (calls/emails) relevant to the department
- **Contextual chat** — Click on any entity (opportunity, job, contact) to open chat panel
- **Call panel** — Real-time inbound/outbound calls for the department
- **Employees list** — Department employees
- **Connected accounts** — Department-scoped integrations

### Setup Flow (2-Step Onboarding)

After registration and business creation, a setup banner guides through 2 steps: Connect Claude (embedded xterm.js terminal) and Build Company Profile (Elena researches the business online, asks a few clarifying questions, saves to `company_profile` JSONB). The 13-person workforce is automatically provisioned on business creation. After setup, the user clicks into any department tab to start working with that team.

New platform connections are synced back to the business profile, keeping it as the single source of truth. All employees reference this profile (from `businesses.company_profile`) for shared business context during conversations.

## Data Flow Across Departments

```
Marketing creates Campaign
    ↓
Campaign gets Business Phone Lines (phones with campaign_name string)
    ↓
Customer calls phone line → Interaction (call, campaign attribution via business_phone_lines)
    ↓ (AI routes to Sales)
Sales creates Opportunity (linked to campaign, contact, call)
    ↓ (contextual chat within Sales workspace)
    ↓ (deal won)
Operations creates Job (linked to opportunity, contact)
    ↓ (contextual chat within Operations workspace)
    ↓ (job completed)
Finance creates Payment (linked to job, opportunity, contact)
    ↓
Notification: payment_received
```

## Task Execution via Department Chat

User describes what they want in a department workspace → department head asks clarifying questions → proposes a task and delegates to specialist employees as needed → specialist employees execute using Bash tool access and internal API endpoints via curl for real-time platform operations. Platform employees (Casey, Quinn, Morgan) handle direct infrastructure calls. Results are returned to the user through the chat interface.

## Department Workspace Profiles

### Sales

**Primary data:** `sales_opportunities` (filtered by department_id='Sales')
**Employees:** Jordan, Riley
**Connections:** CRM integrations, email, Slack
**Key metrics:** Pipeline value, win rate, avg deal size, time to close
**Contextual features:** Chat on opportunities, interaction history, campaign attribution

### Operations

**Primary data:** `jobs` (filtered by department_id='Operations')
**Employees:** Dana, Morgan
**Connections:** Scheduling tools, field service, Slack
**Key metrics:** Active jobs, completion rate, avg job value, utilization
**Contextual features:** Chat on jobs, interaction history, linked opportunities

### Billing

**Primary data:** `payments` (all business payments, viewable by Billing dept)
**Employees:** Quinn (Billing Specialist)
**Connections:** Stripe, Square, QuickBooks, email
**Key metrics:** Revenue, outstanding balance, collection rate, avg payment time
**Contextual features:** Chat on payments, linked jobs/opportunities, customer billing history

### Marketing

**Primary data:** `content_posts`, `media_files`
**Employees:** Elena (CMO), Marcus (SEO Director), Luna (Social Media Director), Alex (Content Creator & Strategist)
**Connections:** Facebook, Instagram, LinkedIn, Google Ads, Google Business, email
**Key features:** Content Studio (compose posts, upload images, publish to connected platforms), campaign tracking, Reports page (pipeline attribution, campaign ROI)
**Contextual features:** Chat with Elena (marketing head), connected accounts with last-posted dates

### IT

**Primary data:** Infrastructure status, connected accounts, system configuration
**Employees:** Casey (Director of IT, Opus)
**Connections:** Claude AI, GitHub, Azure, Ngrok
**Key features:** Chat-first interface — Casey handles website creation (GitHub Pages → Azure), master actions (DB entry management, employee prompt editing, role fixes), infrastructure troubleshooting
**Contextual features:** Chat with Casey (IT head), connected accounts overview, system tools (Claude AI + Ngrok)

### Administration

**Primary data:** Phone settings, business phone lines, IVR config, call logs
**Employees:** Ivy (Director of Administration, Sonnet)
**Connections:** Twilio (shared)
**Key metrics:** Call routing accuracy, response time, system uptime

## Platform Actions

Platform action handlers across 6 integrated platforms:

- **Facebook** — post, get pages, get page photos
- **Instagram** — post, get accounts, get recent media
- **Pinterest** — create pin, get boards
- **Google Analytics** — report, campaign tracking
- **Twilio** — search numbers, provision, list, send SMS, receive calls
- **Stripe** — create customer, create product, create/send invoice, create subscription, list customers, get invoice

Platform employees execute actions via Bash + curl to internal API endpoints (`/api/v1/tools/`). The Claude CLI handles multi-step tool loops internally (search → see results → provision with real data).

## Call Handling & IVR

### Inbound Flow

```
1. Call arrives at business_phone_line.twilio_number
2. Look up BusinessPhoneLine → get campaign_name (string), line_type, department_id
3. Check business hours and after-hours settings
4. If after-hours: play message or forward based on after_hours_action
5. If in-hours: play greeting, gather caller info via IVR
6. AI (Ivy) routes to best department if needed
7. Forward to department.forward_number
8. Create interaction with: department_id, campaign attribution (from business_phone_lines.campaign_name), contact_id, opportunity_id (if known)
9. Tag metadata: "Direct Forward" or "After Hours" or "After Hours Forward"
```

### Outbound Flow

```
1. User in department tab clicks "Call" on a contact/opportunity
2. Look up Department → twilio_number
3. Place call with callerId = department.twilio_number
4. Create interaction with: department_id, contact_id, opportunity_id (if in deal context)
```

### Department-Level Phone Numbers

Each department has:
- `twilio_number` — Outbound caller ID and direct inbound routing
- `twilio_number_sid` — Twilio SID for the number
- `forward_number` — Personal phone for forwarding calls
- `enabled` — Whether the department accepts calls

## Security

- JWT authentication (HS256) with 30-minute access tokens and 7-day refresh tokens
- bcrypt password hashing
- AES-256-GCM encryption for all OAuth tokens and CLI tokens at rest
- Per-business credential isolation
- Department-scoped connection credentials
- OAuth2 Authorization Code flow with PKCE for platform connections
- Tab-based access control for team management (`allowed_tabs` on business_members)
- Claude CLI tokens authenticated via setup-token OAuth flow (not API keys)

## Current Status (March 2026)

### Frontend
- Department-dynamic tab layout (Marketing, Sales, Operations, Billing, IT, Admin, Reports)
- Marketing Content Studio with post composer, image upload, platform selector
- Department workspaces with contextual chat on entities
- Call panel with real-time inbound/outbound call tracking
- Setup banner with 2-step onboarding
- Dark mode with theme persistence

### Database
- 20-table PostgreSQL schema (fully relational, no JSONB storing data)
- Proper dimensional foreign keys on all fact tables
- Campaigns as proper dimension table
- Department-scoped data (opportunities, jobs, payments, campaigns, interactions)
- Phone settings with department-level Twilio numbers

### Employees & Organization
- 13 employees across 6 departments with system prompts stored in DB
- Department-scoped employees (each employee assigned to a department)
- Model tier system (Opus for IT + CEO, Sonnet for department heads, Haiku for specialists)
- No central orchestrator — user interacts directly with department heads

### Task Execution
- Department-scoped task execution through chat interface
- Real-time communication via SSE streaming
- Delivery conversations: completed tasks create review threads

### Platform Integration
- Platform actions across Facebook, Instagram, GA4, Pinterest, Twilio, and Stripe
- Department-scoped connections (Stripe→Billing, Facebook→Marketing, Twilio→shared)
- Platform employees use Bash + curl for real-time API access
- OAuth2 flow for secure credential storage

### CRM & Call Management
- Twilio integration: bring-your-own-account, AI IVR (Ivy), call tracking, SMS logging
- Department-level call panels and call routing
- Campaign tracking with proper dimensional relationships
- Sales opportunities linked to campaigns, contacts, and calls
- Jobs linked to opportunities and contacts
- Payments linked to jobs and opportunities
- Interaction table with full dimensional context

### Notifications & Analytics
- In-app notification system with 7 CRM notification types
- Contextual conversations on entities (opportunities, jobs, contacts)
- Campaign ROI reporting
- Customer lifecycle analytics
- Department performance dashboards

### Email & Billing
- SendGrid/SMTP integration for invoice delivery and follow-up
- Stripe billing with bring-your-own-account model
- Invoice management and subscription handling

### Data Persistence
- All employee system prompts stored in DB (`employees.system_prompt`)
- All conversation data stored in DB (`conversation_messages`)
- All business context stored in DB (`businesses.company_profile`)

## Roadmap & Future

**Near-term (Q2 2026):**
- Enhance campaign attribution with multi-touch modeling
- Build department performance dashboards
- Expand platform integrations (HubSpot, Salesforce)

**Medium-term (Q3-Q4 2026):**
- Advanced call analysis and transcription
- Predictive lead scoring using historical data
- Custom report builder for departments
- Enhanced IVR with AI conversation flows

**Long-term (2027+):**
- Machine learning for opportunity forecasting
- Natural language insights across all departments
- API marketplace for third-party department extensions
- Multi-business management suite

