# NEXA PLATFORM

Modular-monolith SaaS suite scaffold in a single monorepo.

## Stack

- Frontend: Next.js App Router, TypeScript, TailwindCSS, lucide-react, TanStack Query, React Hook Form, Zod
- Backend: FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, PostgreSQL
- Jobs: Celery + Redis (baseline scaffold)
- Dev environment: Docker + Docker Compose

## Repository Structure

- `apps/web` — Next.js web app
- `apps/api` — FastAPI backend
- `packages/shared` — shared contracts/types
- `packages/ui` — shared UI components (shadcn-friendly baseline)
- `infra` — compose + Dockerfiles
- `docs` — architecture and database runbooks

## Prerequisites

- Docker Desktop (with Compose)
- Node.js 22+ (only if running web tooling outside Docker)
- pnpm 10+

## Quickstart

1. Copy env templates if you want local overrides:
   - `.env.example` -> `.env`
   - `apps/api/.env.example` -> `apps/api/.env`
   - `apps/web/.env.example` -> `apps/web/.env.local`
2. Start everything:

```bash
pnpm dev
```

This runs:
- API: http://localhost:8000
- Web: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

Optional pgAdmin profile:

```bash
docker compose -f infra/docker-compose.yml --profile admin up --build
```

## Useful Commands

- Start stack: `pnpm dev`
- Stop stack: `pnpm dev:down`
- Reset stack volumes: `pnpm dev:clean`
- Run migrations: `pnpm migrate`
- Create migration: `pnpm migrate:create -- "add_new_table"`
- Run API tests: `pnpm api:test`
- Run web lint: `pnpm web:lint`
- Run web tests: `pnpm web:test`

## Notes

- This scaffold is single-tenant deployment oriented.
- Foundation for multi-legal-entity, multi-region, and multi-currency context is present in request context and shared types.
- Business logic is intentionally placeholder-only.
