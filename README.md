# Alpago HR Platform

Internal HR automation & streamlining platform for Alpago. Replaces the WhatsApp-and-call coordination with a single, approval-aware system across hiring, onboarding and the employee lifecycle.

## Stack

| Layer | Local dev | Production (Render) |
|---|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic | same |
| Frontend | Next.js 15 · React 19 · JavaScript · Tailwind 4 | same |
| Database | **SQLite** (file-based, zero install) | **PostgreSQL 16** (managed) |
| Jobs / queue | **Celery eager** (in-process, no broker) | **Celery + Redis** |
| Storage | local filesystem fallback | Cloudflare R2 |
| Auth | Auth.js v5 + Google OAuth | same |
| AI | Anthropic Claude API | same |

Same codebase runs on both — the models use SQLAlchemy's dialect-neutral types.

## Project layout

```
alpago-hr/
├── apps/
│   ├── api/              # FastAPI backend
│   └── web/              # Next.js frontend
├── render.yaml           # Render blueprint (production infra as code)
├── .github/workflows/    # CI
└── docs/decisions/       # Architecture decision records (ADRs)
```

## Local development — Windows / Mac / Linux

### Prerequisites

- **Python 3.11+** (`python --version` to check)
- **Node.js 20+** and **pnpm 9+** (`npm install -g pnpm`)
- That's it. No Docker, no Postgres install, no Redis install.

### One-time setup

```bash
# clone and enter
git clone https://github.com/<your-org>/alpago-hr.git
cd alpago-hr

# ── backend ────────────────────────────────────────────────────────
cd apps/api
python -m venv .venv

# activate the venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (Command Prompt):
.venv\Scripts\activate.bat
# Mac / Linux:
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env           # defaults to SQLite, no secrets needed to start
alembic upgrade head           # creates alpago_dev.db
cd ../..

# ── frontend ───────────────────────────────────────────────────────
cd apps/web
cp .env.example .env.local
pnpm install
cd ../..
```

### Daily

Two terminals (no worker needed in dev — Celery runs tasks in-process):

```bash
# Terminal 1 — backend API
cd apps/api
# re-activate venv as above
uvicorn alpago.main:app --reload --port 8000
#  → http://localhost:8000/docs for interactive API

# Terminal 2 — frontend
cd apps/web
pnpm dev
#  → http://localhost:3000
```

### Running tests

```bash
cd apps/api
pytest                    # uses a separate alpago_test.db
```

The approval engine's behaviour contract lives in `tests/test_approval_engine.py` — those tests ARE the spec. Change them deliberately.

## Deploying to Render

Everything is in `render.yaml` (blueprint). First deploy:

1. Push to GitHub (`main` branch).
2. In Render: **New → Blueprint**, point at the repo.
3. Render reads `render.yaml` and provisions: Postgres, Redis, API web service, worker, beat, and the web app.
4. Fill in secrets in Render's dashboard (ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID/SECRET, RESEND_API_KEY, WHATSAPP_TOKEN, R2 keys).
5. Migrations run automatically on the first deploy (`alembic upgrade head` is in the build command).

Expected monthly cost on Starter plans: **~$40–50 USD**.

## Switching from SQLite to Postgres mid-development

When you're ready to use real Postgres locally (e.g. to test JSONB queries), get a free database from [Neon](https://neon.tech) (2-minute signup, no credit card) and point `DATABASE_URL` at it:

```bash
# apps/api/.env
DATABASE_URL=postgresql+psycopg://user:pass@ep-abc.neon.tech/alpago_hr
```

Then `alembic upgrade head` again. The same models + migrations work on both.

## Current status

- [x] Monorepo scaffold
- [x] Local dev environment (SQLite + eager Celery — no Docker required)
- [x] Backend skeleton (FastAPI, SQLAlchemy, Alembic)
- [x] Core data model (users, roles, departments, approvals, notifications, audit)
- [x] Approval workflow engine with tests
- [x] AI service layer (Claude integration)
- [x] Notification service (email, WhatsApp, in-app)
- [x] Frontend skeleton (Next.js, Tailwind theme matching design system)
- [x] Login & dashboard pages
- [x] Render deployment config
- [ ] Google OAuth production credentials
- [ ] WhatsApp Business API templates approved by Meta
- [ ] Hiring module (Weeks 3-4)
- [ ] CV screening (Week 5)
- [ ] Interviews (Week 6)
- [ ] Offers (Weeks 7-8)
- [ ] Joining (Week 9)
