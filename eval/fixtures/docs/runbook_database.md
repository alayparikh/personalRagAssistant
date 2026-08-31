# Database Operations Runbook

## Backup

Full backups run nightly at 02:00 UTC and are retained for thirty days before being aged out to cold storage. Incremental backups run every four hours against the primary and are shipped to a separate availability zone. Restore drills are performed quarterly against a staging cluster to validate the recovery time objective. The team records the wall clock duration of each drill and compares it against the four hour recovery target agreed with business stakeholders. Any drill that exceeds the target opens a follow up task that must be closed before the next quarter begins.

Full backups run nightly at 02:00 UTC and are retained for thirty days before being aged out to cold storage. Additionally, Incremental backups run every four hours against the primary and are shipped to a separate availability zone. Additionally, Restore drills are performed quarterly against a staging cluster to validate the recovery time objective. Additionally, The team records the wall clock duration of each drill and compares it against the four hour recovery target agreed with business stakeholders. Additionally, Any drill that exceeds the target opens a follow up task that must be closed before the next quarter begins.

## Pooling

Application services connect through a connection pooler configured with a maximum of two hundred connections per node. Long running analytical queries are routed to a dedicated read replica rather than the primary so that transactional latency stays predictable. Pool exhaustion alerts fire when utilisation exceeds eighty percent sustained over five minutes. When an alert fires the on call engineer first checks for a runaway query holding a transaction open, then checks whether a recent deploy increased per request query volume.

Application services connect through a connection pooler configured with a maximum of two hundred connections per node. Additionally, Long running analytical queries are routed to a dedicated read replica rather than the primary so that transactional latency stays predictable. Additionally, Pool exhaustion alerts fire when utilisation exceeds eighty percent sustained over five minutes. Additionally, When an alert fires the on call engineer first checks for a runaway query holding a transaction open, then checks whether a recent deploy increased per request query volume.

## Migrations

Schema migrations are applied using an expand and contract pattern so that a rollback never requires data loss. Adding a column is always a separate deployment from backfilling that column, and dropping a column happens at least one full release after the code referencing it has been removed. Every migration is reviewed for lock behaviour, because a migration that takes an exclusive lock on a large table will stall writes for the duration. Migrations expected to run longer than thirty seconds are run out of band.

Schema migrations are applied using an expand and contract pattern so that a rollback never requires data loss. Additionally, Adding a column is always a separate deployment from backfilling that column, and dropping a column happens at least one full release after the code referencing it has been removed. Additionally, Every migration is reviewed for lock behaviour, because a migration that takes an exclusive lock on a large table will stall writes for the duration. Additionally, Migrations expected to run longer than thirty seconds are run out of band.
