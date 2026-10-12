# ADR 001 — Technology stack

**Status:** Accepted · **Date:** 2026-10-10 · **Author:** Solo dev + review by HR lead

## Context

Building the Alpago HR Platform MVP (full end-to-end onboarding) with a single developer in 10 weeks. The stack must be:

- Boring and well-documented (one person can't afford to debug framework edges)
- Strong AI-library ecosystem (Claude integrations throughout)
- Simple to deploy and operate without a dedicated DevOps engineer
- Accessible to a second developer later without major rework

## Decision

| Layer | Choice | Why over alternatives |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Python wins because every AI/OCR/document library has a first-class Python API. FastAPI gives async + type-safe schemas + auto OpenAPI docs. |
| Frontend | Next.js 15 (App Router) + JavaScript | Mature React framework with SSR, API routes for BFF, and healthy ecosystem. Plain JS (.jsx) keeps the toolchain minimal and the stack approachable. |
| DB | PostgreSQL 16 | Relational for structured HR data, JSONB for flexibility (approval chains, AI outputs). One system covers both. |
| Jobs | Celery + Redis | Battle-tested. Retries, scheduling, backoff for free. |
| Storage | Cloudflare R2 | S3-compatible, zero egress fees, ~90% cheaper than S3 at our scale. |
| Auth | Auth.js (NextAuth v5) + Google OAuth | Staff SSO via Google Workspace. Magic links for candidates — no account friction. |
| AI | Anthropic Claude API | Sonnet for standard, Haiku for bulk. Direct SDK, no middleman. |
| Hosting | Render.com | Managed Postgres + Redis + web services + workers in one place. Blueprint YAML for IaC. Starter tier ~$40–50/month covers MVP. |
| CI | GitHub Actions | Zero setup, free for private repos at our volume. |

## Alternatives considered

- **Full-stack Python (FastAPI + HTMX)** — simpler but limits UI complexity for a system that will grow dashboards and interactive forms over 10+ modules.
- **Full-stack Next.js (API routes only)** — tempting for a one-codebase shop, but Python wins for the AI side; keeping the backend separate keeps that door open for a backend engineer later.
- **AWS over Render** — more mature and cheaper at scale, but a massive DevOps learning curve for a solo dev. We can migrate (the stack is standard Docker + PG + Redis) if we outgrow Render.
- **Supabase as a backend** — would collapse auth + db + storage, but weakens the approval engine (we need deep control over state transitions and audit).

## Consequences

- Two languages means two linters, two test runners, two CI jobs. Acceptable.
- Render Starter plans will outgrow us at ~150 users. Review quarterly. Standard tier (~$25/service) handles the next order of magnitude.
- WhatsApp Business API templates must be submitted to Meta in Week 1 to avoid delaying notifications.
