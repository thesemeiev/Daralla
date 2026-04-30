# Sync Refactor Validation

## Scope
- Outbox schema + migrations
- Outbox writers (payment/admin flows)
- Outbox worker loop + retry/dead-letter
- `sync_revision` stale-job protection
- Admin outbox observability and manual retry

## Executed checks (local)
- `python -m compileall apps/backend/src/daralla_backend -q` -> `OK`
- Frontend lint diagnostics for changed files -> no issues

## Manual smoke checklist
- [ ] Migrations apply on clean DB (`006`, `007` present in `schema_version`)
- [ ] Admin subscription update enqueues outbox jobs (`sync_outbox_enqueued > 0`)
- [ ] Worker drains pending jobs (`pending/retry` decrease, `done` grows)
- [ ] Dead jobs can be retried from admin UI (`Outbox синка` action)
- [ ] Stale jobs are auto-skipped when `desired_revision < current sync_revision`
- [ ] Partial payment extension enqueues targeted failed-server jobs
- [ ] Partial new purchase enqueues targeted failed-server jobs

## Production-like acceptance criteria
- [ ] No long-lived `dead` growth without operator action
- [ ] `oldest_due_age_sec` remains bounded under normal load
- [ ] No critical case: DB active/new expiry while panel remains disabled/exhausted after outbox window
