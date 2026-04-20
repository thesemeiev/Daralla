# Architecture Rules

## Layering

- `bot/web/routes/*` is transport only:
  - parse/validate request
  - call service layer
  - map domain errors to HTTP responses
- `bot/services/*` contains business logic and orchestration.
- `bot/db/*` contains persistence only.

## Allowed Dependencies

- `routes -> services`
- `services -> db`
- `routes -X-> db` (direct import is forbidden; enforced by `scripts/check_arch_rules.py`)

## Repo Zones (Monorepo, Single Runtime)

- Backend ownership zone: `apps/backend` (runtime source currently mapped to `bot/`).
- Frontend ownership zone: `apps/frontend` (runtime source currently mapped to `webapp/`).
- Shared FE/BE contracts: `shared/contracts`.

Runtime remains single-service during this stage. Structural split must not break existing entrypoints/deploy.

## API Compatibility

- Existing route URLs and response envelope keys must stay backward-compatible during refactors.
- Breaking API changes require a dedicated ADR and migration note.

## Refactor Safety

- Prefer extraction over rewrite.
- Keep behavior identical first, optimize second.
- Every hotspot split must ship with at least one regression test for the moved behavior.
