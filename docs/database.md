# Database Strategy

## PostgreSQL Schema Pattern

Use predictable table naming with module prefixes:

- `admin_*`
- `crm_*`
- `catalog_*`
- `revenue_*`
- `billing_*`
- `payments_*`
- `support_*`
- cross-cutting tables (for example `audit_logs`) remain unprefixed or use `core_*`

This keeps ownership explicit and avoids accidental coupling.

## Migration Workflow (Alembic)

From repo root:

1. Ensure stack is running (`pnpm dev`)
2. Generate migration:

```bash
pnpm migrate:create -- "short_description"
```

3. Apply migration:

```bash
pnpm migrate
```

4. Commit migration file under `apps/api/alembic/versions`.

## Conventions

- One migration per logical change.
- Keep migrations forward-only where possible.
- Avoid mixing unrelated module changes in a single migration.
- For large data migrations, split schema and backfill phases.

## Initial State

Current scaffold includes a placeholder initial migration creating `audit_logs`.
