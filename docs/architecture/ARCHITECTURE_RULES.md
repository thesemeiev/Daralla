# Architecture Rules

## Layering

- `bot/web/routes/*` is transport only:
  - parse/validate request
  - call service layer
  - map domain errors to HTTP responses
  - keep orchestration minimal (no domain branching that belongs to services)
- `bot/services/*` contains business logic and orchestration.
- `bot/db/*` contains persistence only.

## Allowed Dependencies

- `routes -> services`
- `services -> db`
- `routes -X-> db` (direct import is forbidden; enforced by `scripts/check_arch_rules.py`)
- `telegram handlers -> services` (same use-cases as web routes when applicable)

## Frontend Module Boundaries

- `webapp/js/platform/*` contains Web/Telegram runtime differences only.
- `webapp/js/features/*` contains feature logic and UI orchestration.
- `webapp/js/shared/*` contains reusable helpers (api wrappers, state, formatters, generic UI helpers).
- Feature modules must not call backend directly with ad-hoc fetch logic when shared API clients exist.

## Repo Zones (Monorepo, Single Runtime)

- Backend ownership zone: `apps/backend` (runtime source currently mapped to `bot/`).
- Frontend ownership zone: `apps/frontend` (runtime source currently mapped to `webapp/`).
- Shared FE/BE contracts: `shared/contracts`.

Runtime remains single-service during this stage. Structural split must not break existing entrypoints/deploy.

Reference decision record: `docs/architecture/ADR_0001_MODULAR_MONOLITH_BOUNDARIES.md`.

## API Compatibility

- Existing route URLs and response envelope keys must stay backward-compatible during refactors.
- Breaking API changes require a dedicated ADR and migration note.

## Refactor Safety

- Prefer extraction over rewrite.
- Keep behavior identical first, optimize second.
- Every hotspot split must ship with at least one regression test for the moved behavior.
