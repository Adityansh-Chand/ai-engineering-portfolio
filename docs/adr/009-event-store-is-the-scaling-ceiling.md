# ADR-009 — Keep the shared SQLite event store, and record its ceiling

**Status:** Accepted · **Date:** 2026-08

## Context

Adding `uvicorn` workers does not add much throughput. Retrieval goes from 56.1
to 104.2 requests/second between one and four workers — 1.86× for 4× the
processes — and falls to 49.4 at eight, which is worse than one.

Some of that is four physical cores shared with the load generator. Not all of
it. Every request writes an event through `utils/storage.save_event`, which
opens a connection per write in SQLite's default rollback-journal mode and
re-runs `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` on each
one. Invisible with one process; serialising with several.

Measured on its own, with no model, no HTTP and no retrieval, the shipped store
does **116.0 writes/second across four processes** — and retrieval's measured
ceiling is 104.2 requests/second at the same worker count. The service cannot
outrun its own event log.

The obvious repair was measured before being believed, and it was wrong. Five
strategies, identical schema and statement, median of three repeats, relative to
what ships today:

| processes | shipped | + WAL only | + reuse only | reuse + WAL |
|---|---|---|---|---|
| 2 | 1.00 | 0.80× | 2.11× | **8.26×** |
| 4 | 1.00 | 0.58× | 2.13× | **9.48×** |

Enabling WAL on its own makes it **worse**, in every row. With a connection
opened per write, WAL's per-connection index setup and checkpointing cost more
than the journal it replaces and none of its benefits apply. Connection reuse
alone is about 2×. Together they are 8–9×.

## Decision

**Keep the shared per-service SQLite event store as it is, publish the ceiling,
and record connection reuse plus WAL as the fix to make when it is needed.**

The measurement is the deliverable here, not the change.

## Alternatives considered

**Ship reuse + WAL now.** The measured 8–9× is real and the change is small to
write. Rejected for this round on blast radius rather than on merit: it edits
`utils/storage.py` in five repositories, and a held-open connection is a
different object from a per-call one. `uvicorn` serves on a thread pool, so it
needs `check_same_thread=False` and a write lock; and it has to re-open when
`APP_DB_PATH` changes, or every test that points the store at a temporary file
silently writes to the previous one. Landing that behind a scaling measurement,
unasked, is how a correctness bug arrives disguised as a performance win. It is
scoped as work, with the number that justifies it already in hand.

**Enable WAL and nothing else.** The one-line version, and the one most likely
to be reached for. Rejected because it was measured and it is *negative* —
0.55×–0.80×. Worth recording precisely because it is the plausible change: a
reviewer who assumes WAL is free improvement now has the counter-measurement.

**Give each worker its own database file.** Scales best of anything tested
(4.28× at eight processes). Rejected as a category error rather than on
performance: the event store exists so a request id can be joined into one trace
across a service's workers. Sharding it per worker means a trace lands in
whichever file served the request, which does not make the store faster so much
as stop it being a store.

**Move to Postgres.** The correct answer for a system that needs this, and out
of scope for one that runs on a laptop and spends nothing
([ADR-008](008-model-cost-and-load-locally.md)). It would also make every repo
require a running database to clone and test, trading the portfolio's strongest
property for throughput nothing here needs.

**Stop writing an event per request.** Cheapest possible fix, and it deletes the
feature. The event store is what makes the cross-service trace in
`scripts/trace.py` work at all ([ADR-005](005-request-id-over-opentelemetry.md)).
Sampling would be the real version of this, and it is a bigger design question
than the one being answered here.

## Consequences

- Each service is capped near **100 requests/second** by its event store,
  regardless of worker count, and `docs/SCALE_TEST.md` says so with the
  measurement rather than leaving the earlier "four workers is the peak" reading
  to imply a CPU limit.
- **The recommended fix is now two coupled changes, not one.** Either alone is
  worth roughly nothing — one is actively negative. That is the transferable
  finding, and it would not have been visible from a change that shipped WAL and
  declared victory on the assumption.
- The scaling numbers for `rag` and `sales` are a floor rather than a ceiling for
  the code itself: they measure the service *plus* a store that does not scale.
- The same reflex is at work as in
  [`enterprise-rag-knowledge-system` ADR-003](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system/blob/main/docs/adr/003-reranker-as-measured-null-result.md),
  where the expensive cross-encoder was measured rather than assumed and turned
  out to be worth +0.0011 nDCG. Here the cheap fix was measured rather than
  assumed and turned out to be worth less than nothing.

## Revisit when

Any service needs to sustain more than about 100 requests/second, or the
portfolio runs on more than one machine. At that point reuse + WAL is the first
change, the number justifying it is already measured, and the thread-safety and
`APP_DB_PATH` hazards above are the acceptance criteria for it.
