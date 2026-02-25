# Operations

## Scope
This repository supports operational workflows for local/dev orchestration and container runtime management through Docker Compose.

Primary references:
- `infra/docker-compose.yml`
- `infra/docker/api.Dockerfile`
- `infra/docker/web.Dockerfile`
- `package.json`

## Runtime Topology
Compose services:
- `postgres`
- `redis`
- `api`
- `web`
- optional `pgadmin` profile

Health/dependency behavior:
- `postgres` and `redis` define healthchecks.
- `api` depends on healthy `postgres` + `redis`.
- `web` depends on `api`.

Source reference:
- `infra/docker-compose.yml`

## Deployment Process (as supported)
Current documented process is local/dev deployment:
1. Build and start stack with `pnpm dev`.
2. Apply migrations using `pnpm migrate`.
3. Validate health on `http://localhost:8000/health` and UI on `http://localhost:3000`.

Source references:
- `package.json`
- `README.md`
- `infra/docker-compose.yml`

## Rollback Strategy (current state)
No explicit production rollback automation is defined in repository.

Available local rollback patterns:
- Stop services: `pnpm dev:down`
- Reset persistent volumes: `pnpm dev:clean`
- Rebuild images: `pnpm dev`

Source references:
- `package.json`

## Runtime Config Handling
Config is env-based across stack:
- root env (`.env.example`) drives compose ports and defaults
- API env (`apps/api/.env.example`) drives app/runtime/security flags
- Web env (`apps/web/.env.example`) drives frontend API base and dev token

Source references:
- `.env.example`
- `apps/api/.env.example`
- `apps/web/.env.example`

## CI/CD Configuration
No CI/CD workflow files detected in repository (`.github/workflows` not present).

Open operational implication:
- Build/test/deploy automation location is unknown and should be documented if external.
