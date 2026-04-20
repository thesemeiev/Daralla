# Apps Layout (Transition)

This repository keeps a single runtime, but separates frontend/backend ownership zones.

- `apps/backend` — backend ownership zone (Quart API, Telegram bot, services, db modules).
- `apps/frontend` — frontend ownership zone (SPA/Mini App source and static assets).

Current runtime paths are `apps/backend/src/daralla_backend/` and `apps/frontend/webapp/`.

Architecture model is modular monolith (single runtime, explicit boundaries).
See:
- `docs/architecture/ADR_0001_MODULAR_MONOLITH_BOUNDARIES.md`
- `docs/architecture/ARCHITECTURE_RULES.md`
