# Backup/Restore Drill

## Goal

Verify that DB backups are restorable and service can recover.

## Drill Frequency

- Weekly in staging
- Monthly in production maintenance window

## Procedure

1. Stop service container.
2. Copy latest backup archive to temp directory.
3. Restore `daralla.db` into a clean `data/` folder.
4. Start service and validate:
   - `GET /health` => 200
   - `GET /ready` => 200
   - representative user/subscription records are present
5. Document elapsed time and issues.

## Success Criteria

- Restore completes under agreed RTO.
- No schema mismatch or startup migration failures.
