# Workforce

Department-centric AI automation platform. Users interact directly with department heads — no central orchestrator. Each department is self-sufficient with its own platform tools and capabilities. No cross-department delegation — departments can read shared context but all actions happen within the department's own tab.

## Run

```bash
make setup && source venv/bin/activate
make server        # Backend :8000 — must be a clean terminal (NOT inside Claude Code)
cd frontend && npm run dev  # Frontend :5173
```

Backend calls `claude --print` as a subprocess — fails if `CLAUDECODE=1` is set.

## Code Layout

Backend: `app/core/` (shared), `app/{dept}/` (department-specific — marketing, sales, operations, finance, admin). Each dept folder has routers/, services/, schemas/, models.py as needed. Platform tools (terminal, internal API proxy) live in `app/it/routers/` for now.

Frontend: `frontend/src/shared/` (components, api, stores, hooks, types, lib), `frontend/src/{dept}/` (pages, api, components as needed).

## Source of Truth

DB is the single source of truth for all runtime data. No .md files for employee prompts or business profiles.

- Employee system prompts → `employees.system_prompt` column
- Department documentation → `departments.documentation` column
- Business profiles → dedicated columns on `businesses` table (description, services, target_audience, online_presence, brand_voice, goals, competitive_landscape, profile_source)

## Reference Docs

- `vision.md` — Product vision, org structure, department profiles, roadmap
- `runbook.md` — Database schema (20 tables), platform architecture, deployment

Do not create additional .md doc files. Update what exists.

## Gotchas

- `Interaction.metadata_` — SQLAlchemy reserves `metadata`. Python attr is `metadata_`; DB col is `metadata`; Pydantic serializes as `"metadata"`.
- `CLAUDECODE=1` — Backend must start from a clean terminal or `claude --print` calls fail.
- `business_id=NULL` on departments/employees = system template row; `business_id=UUID` = live business copy.
- Twilio webhooks: `webhook_base_url` lives in `phone_settings` table (DB source of truth), not `.env`. After-hours: `after_hours_action` (message/forward) and `after_hours_forward_number` also in `phone_settings`.
- `business_members` has `is_owner: bool` not a `role` column. Permissions are tab-based via `allowed_tabs`.
- Phone numbers (twilio_number) live on `business_phone_lines` table, linked to departments via `department_id` FK. Call routing config (forward_number, enabled, sms_enabled) lives on `departments` table.
- All fact tables have proper dimensional FKs. No relational data in JSONB.
- Campaign attribution uses `business_phone_lines.campaign_name` (string), not a separate campaigns table.
- Phone lines use `line_type` enum (`mainline`, `tracking`, `department`) instead of `is_mainline` boolean.
- Inbound voice handler tags forwarded calls as "Direct Forward", after-hours as "After Hours" or "After Hours Forward" in interaction metadata.
- Contact status lifecycle: `new` (auto-created on inbound call) → `prospect` (qualified as lead via Sales) → `active_customer` (converted to job) | `no_conversion` | `other`. New callers do NOT appear in Leads until qualified.
- Per-department SMS notifications controlled by `departments.sms_enabled`. Requires A2P 10DLC campaign approval before outbound SMS works.
- Inbound voice handler uses `flush()` for interaction, sets routing metadata, then single `commit()` — never commit before routing metadata is set.
