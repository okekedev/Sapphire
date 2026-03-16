# Workforce

An employee-driven workforce automation platform where 18 AI employees (organized into 6 departments) automate marketing, operations, and business workflows. Users chat with the business assistant to build workflows, and the employee team executes them autonomously via Claude CLI.

## Tech Stack

- **Frontend**: Vite + React 19 + TypeScript + Tailwind v4 + Zustand + TanStack React Query + shadcn/ui
- **Backend**: FastAPI + SQLAlchemy (async) + Pydantic v2
- **Database**: PostgreSQL (19 tables on Supabase)
- **AI**: Claude CLI (`claude --print` with per-employee system prompts stored in DB and model tiers)
- **Auth**: JWT + OAuth2 (14 platforms) + API-key auth (3 platforms) + AES-256-GCM encryption
- **Integrations**: Twilio (voice, SMS, call tracking), Stripe (invoicing, subscriptions), Azure Static Web Apps (website hosting)
- **Real-time**: SSE for live workflow monitoring, xterm.js + WebSocket for terminal auth

## Quick Start

```bash
cp .env.example .env          # Configure environment
make setup                     # Create venv, install deps
source venv/bin/activate      # Activate virtual environment
make server                    # Start backend (:8000) — must be a clean terminal, NOT Claude Code
cd frontend && npm run dev     # Start frontend (:5173)
```

## How It Works

1. User describes what they want in the chat with the assistant
2. Assistant proposes a workflow with employees, steps, and schedules
3. User approves → steps execute sequentially via Claude CLI
4. Each employee runs as `claude --print` with their system prompt (from DB) + business context
5. Platform employees use Bash + curl for real-time API access (Twilio, Stripe, etc.)
6. Real-time monitoring via SSE, notifications on completion/failure
7. Completed workflows create a delivery conversation with the department director for review and approval

## Documentation

| Document | What It Covers |
|----------|---------------|
| `CLAUDE.md` | Setup instructions, quick commands, key files, gotchas |
| `docs/vision.md` | Product vision, org structure, roadmap, department profiles |
| `docs/database-schema.md` | All 19 tables with column definitions |
| `docs/platform.md` | Auth, deployment, employee system, IVR, notifications, shared services |
| `docs/sales.md` | Opportunities, pipeline, per-lead AI |
| `docs/operations.md` | Jobs, documentation-driven work |
| `docs/finance.md` | Payments, Stripe, handoff from jobs |
| `docs/marketing.md` | Campaigns, tracking numbers, attribution, lead generation |
| `docs/admin.md` | Administration: phone infrastructure, Twilio numbers, IVR config |
| `docs/it.md` | Service layer, self-learning system, skills/knowledge hub, usage dashboard |

## Testing

```bash
make test                          # 140 unit tests (~0.5s)
cd frontend && npx tsc -b --noEmit  # Type check
cd frontend && npm run build        # Production build
```

## License

Proprietary — All rights reserved.
