# ADR-005 — Propagate a request ID; do not adopt OpenTelemetry

**Status:** Accepted · **Date:** 2026-05

## Context

Every service already generated a request ID per request and logged it. Each one then threw
it away at the service boundary, so five services produced five independent logs of the
same customer interaction with no way to join them. The identifiers existed and were
wasted, which is worse than not having them.

Answering "what happened when this customer wrote in" required reading five event logs and
correlating by timestamp.

## Decision

Propagate the request ID across service boundaries via `X-Request-ID`, and **store it
beside each event** in every service's event store. `scripts/trace.py` reconstructs a full
cross-service trace by querying each service's `/events` endpoint and joining on the ID.

The event store gained the column through an in-place migration, so existing databases
upgrade rather than needing to be discarded.

## Alternatives considered

**OpenTelemetry with a collector and a tracing backend.** The correct production answer, and
what a real system should do. It gives spans, timing, parent-child relationships, sampling,
and an ecosystem of tooling — none of which is reproduced here.

Rejected on the same constraint that governs everything else in this portfolio: a reviewer
must be able to clone one repository and run it. OTel means an SDK in every service, a
collector to run, and a backend to point at, and a trace that only exists inside Jaeger is
not evidence a reviewer can check from a terminal. What is implemented is join-by-id, which
is the least interesting part of what OTel does and the only part needed to answer the
question above.

The gap is real and stated: **no spans, no durations, no parent-child structure, no
sampling.** The trace says a request touched these services in this order. It does not say
how long any hop took — which is precisely why the load test exists as a separate artifact.

**A correlation ID in logs only, without storing it on events.** Cheaper, and the first
implementation. Rejected because logs here are not queryable over HTTP and the event store
is. Storing it beside the event made the trace assemble from the API surface the services
already expose, with no log shipping at all.

**A dedicated tracing service that services report to.** Rejected as building a worse
Jaeger. If a collector is going to be run, run the real one.

## Consequences

- A single customer interaction is one query away, and the resulting trace is rendered into
  the run report — evidence a reviewer reads rather than infrastructure they install.
- Trace assembly is O(services) HTTP calls and only works while services are up. There is
  no history beyond each service's own event store.
- Because the ID is stored rather than logged, it is queryable through the same
  authenticated `/events` endpoint everything else uses, and it inherits that endpoint's
  auth rather than needing its own.
- Storing the ID on the event was also what surfaced a real bug: an early run report showed
  36 hops for one request because databases persisted across runs. A trace long enough to
  be obviously wrong is a diagnostic that log correlation would not have given.

## Revisit when

Latency attribution across services becomes a question that has to be answered repeatedly
rather than once. The load test answers it once, per endpoint, offline; needing it per
request in production is the point where OTel stops being over-engineering.
