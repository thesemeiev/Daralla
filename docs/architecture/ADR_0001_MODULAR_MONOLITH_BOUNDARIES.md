# ADR-0001: Modular Monolith Boundaries (Single Runtime)

## Status

Accepted

## Date

2026-04-20

## Context

Project runtime is intentionally single-service (`python -m daralla_backend`, one deploy unit), but code ownership spans:

- backend (`apps/backend/src/daralla_backend/`, transition marker `apps/backend`)
- frontend (`apps/frontend/webapp/`, transition marker `apps/frontend`)
- FE/BE contracts (`shared/contracts`)

The main source of coupling is not deployment, but unclear module boundaries in large hotspot files (`apps/frontend/webapp/app.js`, route/service hotspots).

## Decision

We keep a **modular monolith** model with explicit boundaries:

1. Runtime/deploy stays single-service in this stage.
2. Backend remains layered: `routes -> services -> db`.
3. Frontend is split by features and platform adapter:
   - `platform/*` for Telegram/Web differences only
   - `features/*` for business flows (auth, subscriptions, admin)
   - `shared/*` for cross-feature utilities, state, API client glue
4. FE/BE protocol compatibility is controlled by `shared/contracts`.
5. Refactors are extraction-first: preserve behavior, then optimize.

## Consequences

### Positive

- Clear ownership without a risky microservice split.
- Easier testing and code review by module.
- Better change isolation for web/telegram/admin flows.

### Trade-offs

- Transitional duplication may appear temporarily while extracting.
- Requires CI guardrails to prevent backsliding into cross-layer coupling.

## Guardrails

- No direct `daralla_backend.db*` imports in route layer.
- Route handlers stay transport-only (request parsing, service invocation, response mapping).
- Business rules live in service modules.
- Contract changes must update `shared/contracts` artifacts.
