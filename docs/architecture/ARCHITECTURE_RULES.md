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
- `webapp/js/app/*` is the composition layer (state, action registry, feature wiring).
- Feature modules must not call backend directly with ad-hoc fetch logic when shared API clients exist.
- `webapp/app.js` is a thin entrypoint (bootstrap/init), not a feature hotspot.

### Frontend Composition Map

- `webapp/index.html` loads base modules in order.
- `webapp/js/app/state.js` defines centralized mutable UI state defaults.
- `webapp/js/app/composition.js` instantiates all feature modules.
- `webapp/js/app/actions.js` binds passthrough actions to reduce wrapper boilerplate.
- `webapp/app.js` keeps runtime bootstrap, page routing, and minimal glue code.
- `webapp/js/app/dom-bindings.js` maps `data-action`/`data-arg` UI events to the public UI API.
- `webapp/app.js` exposes a whitelist-only public UI API for `dom-bindings` and explicit runtime hooks.

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

## Post-Refactor Freeze Policy

- Architecture refactor is closed; default work mode is feature delivery and bugfixes.
- Structural changes to layers/modules require an ADR before implementation.
- Expanding `webapp/app.js` public UI API requires an ADR with rationale and rollback plan.
- Increasing passthrough wrappers budget above `15` requires an ADR and guardrail update in the same PR.
