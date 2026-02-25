# Documentation Style Guide

This guide defines the required structure and conventions for all module documents in this repository.

## Required Sections Per Module
Each module document in `docs/modules/*.md` must contain:
1. Overview
2. Folder Structure & Key Files
3. Public Interfaces
4. Data Model
5. Execution & Control Flow
6. Configuration
7. Security & Authorization
8. Observability
9. Testing
10. Troubleshooting
11. Open Questions / TODO

## Documentation Conventions
- Prefer factual statements backed by source files.
- Do not infer behavior not visible in code/config.
- If behavior is uncertain, record it under **Open Questions / TODO**.
- Include runtime context (server/browser/worker/CLI/container).

## Code Path Reference Format
- Use repo-relative file paths in inline code.
- Include concrete file paths for every major claim.
- Example formats:
  - `apps/api/app/main.py`
  - `apps/web/app/ops/invoices/page.tsx`
  - `infra/docker-compose.yml`

## Mermaid Diagram Rules
- Use valid Mermaid syntax only.
- Use `flowchart` for architecture/topology and `sequenceDiagram` for control flows.
- Keep one conceptual diagram per flow section unless complexity requires additional diagrams.
- Every diagram should be traceable to at least one source file list directly below it.

## API Documentation Structure
For REST endpoints:
- Method + route
- Purpose
- Request/response model origin
- Auth/permission expectations
- Source references to router + schema/service files

Primary API references in this repo:
- `apps/api/app/api/routes.py`
- `apps/api/app/*/api.py`
- `apps/api/app/*/schemas.py`

## Data Model Documentation Structure
- Model/table groups by domain
- Key relationships
- Constraints or invariants visible in code
- Migration location and execution mechanism

Primary data references in this repo:
- `apps/api/app/**/models.py`
- `apps/api/alembic/env.py`
- `apps/api/alembic/versions/*.py`

## Auth & Security Documentation Pattern
Document in this order:
1. Identity source/auth mechanism
2. Authorization checks (route/service/repository)
3. RLS/FLS enforcement points
4. Audit/security observability hooks
5. Known gaps/TODO comments in code

Primary security references in this repo:
- `apps/api/app/core/auth.py`
- `apps/api/app/core/rbac.py`
- `apps/api/app/platform/security/*.py`
- `apps/web/components/route-guard.tsx`
