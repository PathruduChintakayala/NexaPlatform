# NEXA PLATFORM Documentation Index

- This index file: [`docs/INDEX.md`](INDEX.md)

## Repository Purpose
NEXA PLATFORM is a monorepo for a modular-monolith SaaS foundation combining a FastAPI backend, a Next.js App Router frontend, shared TypeScript packages, and Docker-based local infrastructure. It provides CRM, admin/authz, sales, ops, billing/payments, ledger, and reporting workflows through a single deployable stack.

Primary source references:
- `README.md`
- `apps/api/app/main.py`
- `apps/web/app/layout.tsx`
- `infra/docker-compose.yml`

## Tech Stack Summary
- Frontend: Next.js 15, React 19, TypeScript, Tailwind, TanStack Query (`apps/web/package.json`)
- Backend: FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, JWT (`apps/api/pyproject.toml`, `apps/api/app/core/auth.py`)
- Data/Infra: PostgreSQL, Redis, Docker Compose (`infra/docker-compose.yml`)
- Build/Workspace: pnpm workspaces and TypeScript (`package.json`, `pnpm-workspace.yaml`)

## High-Level Architecture
```mermaid
flowchart LR
  Web[apps/web Next.js] -->|HTTP /api/*| API[apps/api FastAPI]
  API --> DB[(PostgreSQL)]
  API --> Cache[(Redis)]
  API --> Metrics[/metrics Prometheus format/]
  API --> Events[In-process Event Bus]
  Web --> Shared[@nexa/shared]
  Web --> UI[@nexa/ui]
```

Architecture source references:
- `apps/web/lib/api/core.ts`
- `apps/api/app/api/routes.py`
- `apps/api/app/core/database.py`
- `apps/api/app/core/events.py`
- `apps/api/app/metrics.py`

## Detected Modules
1. **api** — FastAPI application with CRM, authz, catalog, revenue, subscription, billing, payments, ledger, and reporting domains.
   - Doc: [`docs/modules/api.md`](modules/api.md)
2. **web** — Next.js App Router UI with route hubs, domain pages, API clients, query state, and guard components.
   - Doc: [`docs/modules/web.md`](modules/web.md)
3. **infra** — Docker Compose stack and Dockerfiles for local runtime orchestration.
   - Doc: [`docs/modules/infra.md`](modules/infra.md)
4. **packages-shared** — Shared TypeScript contracts and scope primitives.
   - Doc: [`docs/modules/packages-shared.md`](modules/packages-shared.md)
5. **packages-ui** — Shared UI primitives consumed by apps.
   - Doc: [`docs/modules/packages-ui.md`](modules/packages-ui.md)

Module detection references:
- `apps/`
- `packages/`
- `infra/`
- `pnpm-workspace.yaml`

## Cross-Cutting Documents
- [`docs/architecture.md`](architecture.md)
- [`docs/SECURITY.md`](SECURITY.md)
- [`docs/OBSERVABILITY.md`](OBSERVABILITY.md)
- [`docs/DEVELOPMENT.md`](DEVELOPMENT.md)
- [`docs/OPERATIONS.md`](OPERATIONS.md)
- [`docs/STYLE_GUIDE.md`](STYLE_GUIDE.md)

## Legacy/Pre-existing Docs
- [`docs/database.md`](database.md)
