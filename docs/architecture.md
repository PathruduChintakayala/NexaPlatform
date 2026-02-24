# Architecture

## High-Level

This repository uses a **modular monolith** approach:

- One deployable API service (`apps/api`)
- One deployable web service (`apps/web`)
- Shared cross-cutting packages (`packages/shared`, `packages/ui`)

## Module Boundaries

Backend module skeletons live in:

- `app/modules/admin`
- `app/modules/crm`
- `app/modules/catalog`
- `app/modules/revenue`
- `app/modules/billing`
- `app/modules/payments`
- `app/modules/support`

Boundary rules:

1. A module owns its domain models, application services, and API routes.
2. Cross-module calls must occur through explicit service interfaces/events.
3. Cross-cutting concerns belong under `app/core` or shared packages.

## Cross-Cutting Components

### Request Context

`RequestContextMiddleware` enriches each request with:

- `request_id`
- `legal_entity`
- `region`
- `currency`
- `user_id` (when available)

This provides the foundation for jurisdiction and currency-aware behavior.

### Auth + RBAC

- `app/core/auth.py`: JWT verification stub (`get_current_user`)
- `app/core/rbac.py`: permission hook placeholder (`require_permissions`)

TODO: Integrate real IdP and policy engine.

### Audit

- `app/models/audit.py`: `audit_logs` table model
- `app/services/audit.py`: `write_audit_log` helper

TODO: call from module command handlers and critical write paths.

### Event Bus

- `app/core/events.py`: in-process publish/subscribe abstraction

Use this for decoupled internal domain events inside the monolith. If async/event streaming is needed later, replace implementation while preserving interface.

### Background Jobs

- `app/core/celery_app.py`: Celery baseline wired to Redis

TODO: add dedicated worker process and task modules per bounded module.
