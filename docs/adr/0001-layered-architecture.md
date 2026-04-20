# ADR 0001: Layered Architecture For Backend

- Status: Accepted
- Date: 2026-04-20

## Context

Backend routes and domain logic have grown inside the same files, making change impact hard to predict.

## Decision

Adopt and enforce `routes -> services -> db` layering.

## Consequences

- Better readability and testing boundaries.
- Refactors become incremental instead of high-risk rewrites.
- Transitional direct DB imports in routes are tracked and must be reduced.
