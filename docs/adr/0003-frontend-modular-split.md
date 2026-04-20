# ADR 0003: Frontend Modular Split Strategy

- Status: Accepted
- Date: 2026-04-20

## Context

`apps/frontend/webapp/app.js` is a large monolithic file with mixed concerns.

## Decision

Split by responsibility without changing runtime behavior:

- `apps/frontend/webapp/js/api/*` for API client logic
- `apps/frontend/webapp/js/ui/*` for reusable UI messaging
- keep legacy global functions as wrappers while migrating

## Consequences

- Incremental migration path with no build-system migration required.
- Existing inline HTML handlers keep working during transition.
