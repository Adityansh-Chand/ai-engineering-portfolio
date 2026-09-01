# ADR-012 — Ship the event store fix

**Status:** Accepted · **Date:** 2026-09 · **Supersedes:**
[ADR-009](009-event-store-is-the-scaling-ceiling.md)

## Context

[ADR-009](009-event-store-is-the-scaling-ceiling.md) established that
`utils/storage.save_event` was the throughput ceiling for every service —
flat at about 168 writes/second no matter how many worker processes ran —
and that the fix was two coupled changes worth 8–9× in isolation. It then
deliberately did **not** make the change, on blast radius: five repositories, a
thread-safety requirement, and a way for a cached connection to silently write
to the wrong database if `APP_DB_PATH` moved.

Those hazards are real and they are also enumerable, which makes them
acceptance criteria rather than reasons to stop. Deferring twice would be a
decision to keep a measured defect because fixing it is work.

## Decision

**Make the change: one connection per thread, opened once, in WAL mode.**

Thread-local rather than a single connection behind a global lock — under WAL a
reader does not block the writer, so `recent_events` has no reason to queue
behind `save_event`. The connection is keyed on the resolved `APP_DB_PATH` and
reopens when it changes.

Applied identically to all five services, consistent with
[ADR-003](003-duplicated-template-over-shared-library.md): the template is
duplicated on purpose, so a fix to it is duplicated too.

## What it bought

Store in isolation, median of three repeats, writes/second:

| processes | connection-per-write | + WAL only | shipped (reuse + WAL) | isolated files |
|---|---|---|---|---|
| 1 | 186.2 | 157.5 (0.85×) | **900.6 (4.84×)** | 861.8 |
| 2 | 172.9 | 77.0 (0.45×) | **881.3 (5.10×)** | 1626.4 |
| 4 | 168.5 | 116.3 (0.69×) | **848.0 (5.03×)** | 2776.4 |
| 8 | 168.3 | 141.3 (0.84×) | **893.6 (5.31×)** | 3200.3 |

At the HTTP level, peak requests/second before and after:

| endpoint | 1 worker before → after | best point before → after |
|---|---|---|
| `rag /v1/query` | 56.1 → **144.7** | 104.2 (4 workers) → **230.3** (8 workers) |
| `sales /v1/score` | 50.2 → **152.5** | 77.5 → **222.6** |
| `ops /v1/decide` | 46.3 → **59.0** | 46.3 → **89.2** |

Two results are worth more than the headline multiple.

**The store was throttling a single worker.** Retrieval nearly tripled at one
worker, where there is no cross-process contention at all. The cost was never
really lock contention — it was opening a connection and re-running four schema
statements on every request.

**The fan-out endpoint was never a fan-out problem.** ADR-009 read `ops
/v1/decide` getting monotonically worse with more workers (0.59× at eight) as
the expected lesson that front-door capacity is not downstream capacity. It was
mostly the downstream services being store-bound. With the store fixed, the same
endpoint scales to 1.51× at eight workers. **The earlier interpretation was
wrong, and it was wrong in a way that sounded like architectural wisdom** —
which is the more useful half of this record.

## Alternatives considered

**Keep deferring.** ADR-009's position, and defensible once. Rejected on
repetition: the hazards it named are a checklist, and a measured 5× left unmade
because the fix requires care is a decision to prefer the appearance of
discipline to the work.

**Ship WAL only, as the smaller change.** Rejected again and for the same
measured reason: it is *negative*, 0.45–0.85×. Recorded twice because it is the
change a reviewer is most likely to suggest.

**A single connection per process behind a lock.** Simpler to reason about, and
what the probe originally measured. Rejected because it serialises reads behind
writes for no benefit under WAL.

**Per-worker database files.** Still the fastest option measured — 3200
writes/second at eight processes, against 894 shared. Rejected on the same
grounds as in ADR-009: it makes the request-id trace land in whichever file
served the request, which does not speed up the store so much as stop it being
one.

## Consequences

- **The event store is no longer the binding constraint.** It is still flat
  across process counts — writes to one file serialise — but at roughly 870
  writes/second against endpoints that peak near 230 requests/second, it is no
  longer what limits them. The fix raised a ceiling; it did not make the store
  scale, and `docs/SCALE_TEST.md` says so.
- **`shipped` measures ~870 where the prototype measured ~1400.** The
  difference is `_db_path()` rebuilding a `Path` from the environment on every
  call to check whether the cached connection is still valid. That is the price
  of the `APP_DB_PATH` safety, it is known, and it is not worth optimising while
  the store sits four times above what the services ask of it.
- **Committed load and cost figures are now stale in the conservative
  direction.** `docs/LOAD_TEST.md` and everything derived from it were measured
  against the slower store, so the cost model overstates compute per request.
  Not restated here, because re-running them is its own measurement rather than
  an edit.
- WAL adds `-wal` and `-shm` sidecar files. `scripts/service_harness.py` deletes
  them alongside the database, since committed events can sit in the sidecar and
  deleting only the database would resurrect them on the next open — the exact
  stale-store bug that delete exists to prevent.

## Revisit when

Any service needs to sustain more than about 800 requests/second, at which point
the store is the constraint again and the honest answer is Postgres rather than
a fourth round of SQLite tuning.
