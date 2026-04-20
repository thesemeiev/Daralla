# ADR 0002: API Compatibility During Refactor

- Status: Accepted
- Date: 2026-04-20

## Context

Frontend, Telegram Mini App, and admin interfaces depend on current endpoint contracts.

## Decision

During hotspot decomposition:

- keep route paths stable
- keep core response fields stable
- avoid broad semantic changes in the same PR as structure changes

## Consequences

- Lower regression risk in production.
- Easier rollback because behavior remains constant.
