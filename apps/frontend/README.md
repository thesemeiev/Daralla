# Frontend Ownership Zone

Primary frontend source remains in `webapp/` during transition.

Scope:
- SPA pages and UI flows
- browser-side API client usage
- static assets and styles

Current entrypoint:
- `webapp/index.html`

Target decomposition during transition:
- `webapp/js/platform/*` for Telegram/Web runtime differences
- `webapp/js/features/*` for business feature flows
- `webapp/js/shared/*` for reusable helpers/state/api glue
