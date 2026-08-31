# ADR-001 — Enrichment may improve a decision, never prevent one

**Status:** Accepted · **Date:** 2026-05

## Context

Five services were built to run standalone, and each one does: clone the repository, set
nothing, and it works. That property is the portfolio's strongest asset — a reviewer can
check any single claim without orchestrating anything.

Connecting them threatens exactly that. The obvious integration — ops calls sales for an
account score, calls incident for outage status, calls retrieval for grounding — makes four
services into dependencies of one, and the standalone property is gone the moment a call
becomes required.

The forcing question: what has to be true for integration not to cost the thing that made
these worth integrating?

## Decision

**An enrichment may improve a decision. It may never prevent one.**

Every cross-service call sits behind configuration (`SALES_API_URL`, `INCIDENT_API_URL`,
`RAG_API_URL`). Unset, unreachable, slow, or returning nonsense, the caller receives `None`
plus a reason code and continues with the decision it would have made alone. Three
protections enforce it: a short explicit timeout, exactly one retry, and a circuit breaker.

Every enrichment outcome — `ok`, `not_configured`, `timeout`, `circuit_open`, `error` — is
recorded **in the response body**, so a reader can tell from the response alone whether an
enrichment was live or fell back.

## Alternatives considered

**Required dependencies with health checks and startup ordering.** The conventional
microservice answer, and it is what `depends_on` in the compose file suggests. Rejected
because it converts five independently reviewable services into one system that only works
assembled. It also cannot express the actual topology: ops calls incident and incident
pushes to ops, a cycle compose cannot order.

**A single service.** Genuinely simpler, and the honest observation is that five services
for this workload is more architecture than the problem needs. Rejected because the
independence is deliberate — each service is a separate reviewable artifact with its own
evaluation, and merging them would trade that for an operational simplicity nobody here
needs.

**Graceful degradation without a circuit breaker** — timeout and fall back, no state. This
is nearly right and was the first implementation. The load test shows what it misses: with
the dependency dead and the breaker absent, p95 sits at **4243 ms** because every request
pays a connection failure plus a retry before falling back. The fallback works and is
expensive. With the breaker open, p95 is **145 ms** — the healthy figure. The breaker's job
is not making failure survivable; the fallback already does that. It is not paying full
price for a failure that is not going to stop.

**Caching enrichments instead of failing.** Rejected. A stale account score presented as
current is worse than a decision made without one, and the response could no longer
honestly say which it had.

## Consequences

- Every enrichment call site has two paths, and both need testing. The integration tests
  assert the connected path *and* the degraded path, which roughly doubles that suite.
- Responses carry outcome codes that are noise when everything works. Accepted: they are
  the only thing that makes degradation visible rather than invisible.
- The system is measurably **faster while degraded** (p95 145.2 ms open, 145.3 ms healthy)
  because it stops making a call. That reads as a paradox and is just the trade: enrichment
  costs latency, and losing it refunds the latency.
- A reviewer can still check any single service without the others, which is the whole
  point and is verified by every repository's own CI running alone.

## Revisit when

An enrichment becomes genuinely load-bearing — something a decision is wrong without rather
than weaker without. At that point it is not an enrichment and this ADR does not apply to
it; it needs a real dependency with the operational consequences that implies, recorded
separately.
