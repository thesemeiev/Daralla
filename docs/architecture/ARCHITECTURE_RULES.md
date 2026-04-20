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
- `routes -X-> db` (direct import is transitional and must be reduced)

## API Compatibility

- Existing route URLs and response envelope keys must stay backward-compatible during refactors.
- Breaking API changes require a dedicated ADR and migration note.

## Refactor Safety

- Prefer extraction over rewrite.
- Keep behavior identical first, optimize second.
- Every hotspot split must ship with at least one regression test for the moved behavior.
