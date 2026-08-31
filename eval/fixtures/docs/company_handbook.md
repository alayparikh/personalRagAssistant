# Acme Robotics Engineering Handbook

## Deployment Policy
All production deploys require two approvals and must run during the
deploy window of 10:00-16:00 Eastern on weekdays. Friday deploys are
prohibited without a written exception from the on-call lead.

## Incident Severity Levels
- SEV1: complete outage affecting all customers. Page immediately.
- SEV2: degraded service or partial outage. Page during business hours.
- SEV3: minor issue with a workaround available. File a ticket.

## Code Review
Every pull request needs at least one approving review. Changes touching
authentication or billing need review from the security team.
