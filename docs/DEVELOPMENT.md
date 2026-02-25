# Development Guide

## Local Setup
Prerequisites:
- Docker Desktop with Compose
- Node.js 22+ and pnpm 10+ (if running web tooling outside containers)

References:
- `README.md`
- `package.json`

## Environment Setup
Optional env copy flow:
- `.env.example` → `.env`
- `apps/api/.env.example` → `apps/api/.env`
- `apps/web/.env.example` → `apps/web/.env.local`

Source references:
- `.env.example`
- `apps/api/.env.example`
- `apps/web/.env.example`

## Run Backend + Web via Docker
- Start: `pnpm dev`
- Stop: `pnpm dev:down`
- Reset volumes: `pnpm dev:clean`

Source references:
- `package.json`
- `infra/docker-compose.yml`

## Backend Development (API)
Common commands (containerized):
- Run migrations: `pnpm migrate`
- Create migration: `pnpm migrate:create -- "message"`
- Run tests: `pnpm api:test`

Direct API module commands:
- `poetry run pytest` from `apps/api`

Source references:
- `package.json`
- `apps/api/pyproject.toml`
- `apps/api/alembic.ini`

## Web Development
Commands:
- `pnpm --filter @nexa/web dev`
- `pnpm --filter @nexa/web test`
- `pnpm --filter @nexa/web lint`
- `pnpm --filter @nexa/web typecheck`

Source references:
- `apps/web/package.json`
- root `package.json`

## Repo Scripts
Root scripts (`package.json`):
- `dev`, `dev:down`, `dev:clean`
- `migrate`, `migrate:create`
- `api:test`, `web:lint`, `web:test`
- `lint`, `format`

## Coding/Project Conventions (from code)
- Monorepo package boundaries via pnpm workspaces (`pnpm-workspace.yaml`).
- Backend strict typing/lint setup in Poetry config (`apps/api/pyproject.toml`).
- Web uses App Router and React Query provider (`apps/web/app/layout.tsx`, `apps/web/app/providers.tsx`).
- Shared package transpilation in Next config (`apps/web/next.config.ts`).

## Open Questions / TODO
- No centralized contributor style/contribution doc detected; if desired, add contribution standards and branching/release workflow.
