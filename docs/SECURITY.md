# Security Documentation

## Authentication Architecture
Backend authentication is token-based using JWT decode from `Authorization: Bearer`.
- Decoder and user principal: `apps/api/app/core/auth.py`
- `/me` identity endpoint: `apps/api/app/api/routes.py`
- Guest fallback behavior for missing/invalid token currently returns `anonymous/guest`.

Frontend uses local storage token and lightweight client-role checks:
- `apps/web/components/route-guard.tsx`
- `apps/web/lib/api/core.ts`

## Authorization Model
Authorization is layered:
1. Route-level permission checks (`require_permissions`) (`apps/api/app/core/rbac.py`)
2. Policy backend evaluation (in-memory or DB-backed) (`apps/api/app/platform/security/policies.py`)
3. Repository-level RLS/FLS checks (`apps/api/app/platform/security/rls.py`, `apps/api/app/platform/security/fls.py`, `apps/api/app/platform/security/repository.py`)

Policy backend selection:
- Controlled by `authz_policy_backend` and environment auto-selection in `apps/api/app/main.py`.

## Enforcement Points
- Router dependency checks in domain `api.py` files under `apps/api/app/**/api.py`.
- Security context model: `apps/api/app/platform/security/context.py`.
- RLS denied actions emit audit + metrics: `apps/api/app/platform/security/rls.py`.
- FLS masking/denial emits audit + metrics: `apps/api/app/platform/security/fls.py`.

## How to Add New Permission/Role
Current code path:
1. Define/create permission records via admin API (`apps/api/app/authz/api.py`).
2. Assign permissions to roles (`apps/api/app/authz/api.py`).
3. Assign roles to users (`apps/api/app/authz/api.py`).
4. Enforce in route/service/repository:
   - route: `require_permissions(...)` (`apps/api/app/core/rbac.py`)
   - data-level: leverage `BaseRepository` security wrappers (`apps/api/app/platform/security/repository.py`).

## Audit & Metrics Overview
- Audit event capture utility: `apps/api/app/audit.py`.
- Security-related metrics:
  - `fls_masked_fields_count`, `fls_denied_fields_count`
  - `rls_denied_reads_count`, `rls_denied_writes_count`
  - authz cache/db metrics
  in `apps/api/app/metrics.py`.
- Correlation propagation:
  - API middleware (`apps/api/app/middleware/correlation_id.py`)
  - Web request wrapper (`apps/web/lib/api/core.ts`)

## Open Questions / TODO
- Guest fallback on JWT decode failure may be unsuitable for strict environments (`apps/api/app/core/auth.py` TODO).
- Confirm whether route-level frontend guards are sufficient UX-only controls or if server-side rendering guards are planned.
- Confirm production default for `authz_default_allow` in security-sensitive deployments (`apps/api/app/core/config.py`).
