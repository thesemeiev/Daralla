# Backend Ownership Zone

Primary backend source remains in `apps/backend/src/daralla_backend/` during transition.

Scope:
- Quart routes and app bootstrap
- service layer
- persistence modules
- Telegram handlers and startup runtime

Runtime entrypoints are unchanged:
- `PYTHONPATH=apps/backend/src python -m daralla_backend`

Boundary reminder:
- route layer stays transport-only
- business logic belongs to `apps/backend/src/daralla_backend/services/*`
- persistence stays in `apps/backend/src/daralla_backend/db/*`
- shared route transport helpers live under `apps/backend/src/daralla_backend/web/routes/*` (response/error mapping only)

Route-layer convention:
- parse request data
- invoke service functions
- map service/domain errors to HTTP responses
- avoid direct imports from any `daralla_backend.*.db*` module in routes
