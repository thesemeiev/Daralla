# Operations Runbook

## Health Checks

- Liveness: `GET /health` must return `200`.
- Readiness: `GET /ready` must return `200` and checks with `db=ok`.
- Metrics: `GET /metrics` should expose non-empty counters after traffic.

## Incident: Webhook Failures

1. Check `webhook_failed_total` counters in `/metrics`.
2. Inspect logs for provider (`yookassa` or `cryptocloud`).
3. Validate webhook secret configuration in environment.
4. Retry from provider side if payload is valid.

## Incident: Sync Errors

1. Inspect `background_task_error_total|task=full_sync`.
2. Validate X-UI connectivity and panel responsiveness.
3. Confirm DB is writable and not locked for long periods.

## Incident: Post-Deploy Degradation

1. Verify container health status in Docker.
2. Call `/health` and `/ready` directly on localhost.
3. If failing, rollback to previous image/container snapshot.
