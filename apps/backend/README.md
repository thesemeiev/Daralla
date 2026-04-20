# Backend Ownership Zone

Primary backend source remains in `bot/` during transition.

Scope:
- Quart routes and app bootstrap
- service layer
- persistence modules
- Telegram handlers and startup runtime

Runtime entrypoints are unchanged:
- `python -m bot`
