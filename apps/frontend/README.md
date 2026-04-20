# Frontend Ownership Zone

Primary frontend source remains in `apps/frontend/webapp/` during transition.

Scope:
- SPA pages and UI flows
- browser-side API client usage
- static assets and styles

Current entrypoint:
- `apps/frontend/webapp/index.html`

Target decomposition during transition:
- `apps/frontend/webapp/js/platform/*` for Telegram/Web runtime differences
- `apps/frontend/webapp/js/features/*` for business feature flows
- `apps/frontend/webapp/js/shared/*` for reusable helpers/state/api glue
- `apps/frontend/webapp/js/app/*` for composition root (`state.js`, `composition.js`, `actions.js`)

Thin-entry target:
- `apps/frontend/webapp/app.js` keeps bootstrap and init only
- feature instantiation is centralized in `apps/frontend/webapp/js/app/composition.js`
