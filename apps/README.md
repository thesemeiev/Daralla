# Apps Layout (Transition)

This repository keeps a single runtime, but separates frontend/backend ownership zones.

- `apps/backend` — backend ownership zone (Quart API, Telegram bot, services, db modules).
- `apps/frontend` — frontend ownership zone (SPA/Mini App source and static assets).

During transition, runtime paths stay backward-compatible (`bot/` and `webapp/` remain active).
