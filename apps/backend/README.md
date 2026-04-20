# Backend Ownership Zone

Primary backend source remains in `bot/` during transition.

Scope:
- Quart routes and app bootstrap
- service layer
- persistence modules
- Telegram handlers and startup runtime

Runtime entrypoints are unchanged:
- `python -m bot`

Boundary reminder:
- route layer stays transport-only
- business logic belongs to `bot/services/*`
- persistence stays in `bot/db/*`
- shared route transport helpers live under `bot/web/routes/*` (response/error mapping only)

Route-layer convention:
- parse request data
- invoke service functions
- map service/domain errors to HTTP responses
- avoid direct imports from any `bot.*.db*` module in routes
