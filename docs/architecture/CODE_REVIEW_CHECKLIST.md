# Code Review Checklist

## Architecture

- Route handler does not contain business logic loops or DB orchestration.
- Service method has explicit inputs/outputs and no hidden side effects.
- DB module does not leak HTTP/Telegram specifics.

## Reliability

- New paths include structured logs with enough context.
- Errors are handled with actionable messages.
- Critical flows (auth/payment/subscription/sync) have regression tests.

## Compatibility

- Existing public API contracts remain stable (status codes and response keys).
- Migration notes exist for any behavior change.

## Operations

- Health/readiness checks are not broken.
- Metrics/counters are updated for new background jobs and webhooks.
