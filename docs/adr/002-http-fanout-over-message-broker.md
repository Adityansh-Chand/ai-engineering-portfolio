# ADR-002 — HTTP fan-out and an outbox, not a message broker

**Status:** Accepted · **Date:** 2026-05

## Context

Four of the five edges in this system are synchronous pulls: a service asks a question and
waits. One is not. The incident platform is named for noticing a problem and telling
someone *unprompted* — an incident opening triggers outreach to customers who recently
complained about that service. Pull cannot express that.

Push is where distributed systems get hard, and the honest options were a real broker
(Kafka, RabbitMQ, Redis Streams, SQS) or HTTP webhooks with the failure handling that makes
push survivable.

## Decision

HTTP fan-out to configured subscribers, with an **outbox**, exponential-backoff retries, a
**dead-letter queue**, and **at-least-once** delivery with stable `event_id`s that
subscribers deduplicate on.

`EVENT_SUBSCRIBERS` configures it. Unset, the platform simply stops publishing.

Four failure modes are handled because they are the ones that actually bite:

| problem | handling |
|---|---|
| detection must not block on delivery | in-memory outbox, background delivery worker |
| delivery fails | exponential backoff retry, not drop-on-first-error |
| retries mean duplicates | at-least-once, stable `event_id`, idempotent consumers |
| some events never deliver | dead-letter queue at `GET /events/dlq`, not silence |

## Alternatives considered

**A real broker.** The correct answer for a system that needs durability, replay,
partitioning, consumer groups, or ordering. Rejected on a cost this portfolio will not pay:
every repository must run standalone from a fresh clone with nothing configured. Adding a
broker makes it infrastructure a reviewer has to stand up before anything works, and it
would be infrastructure carrying two event types.

The important part is what that costs, stated rather than glossed: **there is no durable
log, no partitioning, no consumer groups, and the outbox is lost on restart.** Events in
flight when the process dies are gone. That is a real limitation of a real design, not a
simplification of one.

**Synchronous push — call the subscriber inline.** Simplest possible. Rejected because
scoring a minute of telemetry would then wait on a subscriber's HTTP stack, and a slow
subscriber would degrade detection itself. The thing being protected is the detector, not
the delivery.

**Polling — let ops ask incident periodically.** No new machinery, and the existing pull
edge already does something like it. Rejected because it turns "tell someone now" into
"find out within the poll interval", which is the property the service exists to have.
Every poll interval short enough to be useful costs more requests than the events would.

**Claiming exactly-once delivery.** Rejected as a lie. A delivery that succeeded with a
lost acknowledgement is indistinguishable from one that failed. At-least-once with
idempotent consumers is what is actually implemented, so it is what is documented.

## Consequences

- The push edge works, is demonstrable end to end, and degrades cleanly: remove
  `EVENT_SUBSCRIBERS` and detection carries on without publishing.
- Consumers must be idempotent, which is a real constraint on anything subscribing later.
  The ops service deduplicates on `event_id`.
- Restart loses the outbox. Documented, not worked around, because working around it means
  durability, and durability means the broker this ADR rejected.
- Ops calls incident and incident pushes to ops, which is a cycle `docker compose` cannot
  order with `depends_on`. It does not need to: the bus retries with backoff, so incident
  starting first is fine and early events simply redeliver once ops is up.
- The system cannot replay history, which rules out rebuilding subscriber state from the
  event log — a capability a broker would have given nearly free.

## Revisit when

A second producer appears, or a subscriber needs to rebuild its state by replaying. Either
one makes the durable log the cheaper option, and at that point the outbox pattern here
becomes the adapter in front of it rather than something to throw away.
