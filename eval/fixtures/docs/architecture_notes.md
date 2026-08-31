# Platform Architecture Notes

## Boundaries

Each service owns its own datastore and no service reads another service's tables directly. Cross service reads go through published interfaces so that internal schema changes remain internal and do not create hidden coupling between teams. When a new read pattern is needed the owning team publishes an endpoint rather than granting database access. This rule has occasionally slowed delivery but has repeatedly prevented schema changes from breaking unrelated systems.

Each service owns its own datastore and no service reads another service's tables directly. Additionally, Cross service reads go through published interfaces so that internal schema changes remain internal and do not create hidden coupling between teams. Additionally, When a new read pattern is needed the owning team publishes an endpoint rather than granting database access. Additionally, This rule has occasionally slowed delivery but has repeatedly prevented schema changes from breaking unrelated systems.

## Eventbus

Domain events are published to a durable topic with at least once delivery semantics. Consumers are required to be idempotent because redelivery is an expected condition rather than an exceptional one. Every event payload carries a schema version so that producers and consumers can evolve independently. Consumers that fall behind by more than an hour raise an alert, since a slow consumer usually indicates a poison message rather than genuine load.

Domain events are published to a durable topic with at least once delivery semantics. Additionally, Consumers are required to be idempotent because redelivery is an expected condition rather than an exceptional one. Additionally, Every event payload carries a schema version so that producers and consumers can evolve independently. Additionally, Consumers that fall behind by more than an hour raise an alert, since a slow consumer usually indicates a poison message rather than genuine load.

## Caching

Read heavy endpoints use a short lived cache with a sixty second time to live. Cache keys always include the tenant identifier so that a cached response can never cross a tenant boundary, which is the failure mode with the most severe consequences. Invalidation is time based rather than event based, trading a small window of staleness for a substantially simpler and more predictable system.

Read heavy endpoints use a short lived cache with a sixty second time to live. Additionally, Cache keys always include the tenant identifier so that a cached response can never cross a tenant boundary, which is the failure mode with the most severe consequences. Additionally, Invalidation is time based rather than event based, trading a small window of staleness for a substantially simpler and more predictable system.
