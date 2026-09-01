# Horizontal scaling, and the ceiling it finds

`docs/LOAD_TEST.md` measured one worker per service under rising concurrency and
found throughput peaking around four concurrent requests and then falling. That
left the obvious question open: the peak is a property of *one process*, so what
happens with more of them?

This answers it, and the answer turned out to be about the event store rather
than about workers.

```bash
python scripts/scale_test.py
```

Results: [`docs/assets/scale-test.json`](assets/scale-test.json) ·
card: [`docs/assets/scale-test.svg`](assets/scale-test.svg)

## Method

Peak throughput at 1, 2, 4 and 8 `uvicorn` workers. Peak is found by sweeping
concurrency (4, 8, 16) at each worker count rather than reusing the
single-worker peak -- eight workers measured at the concurrency that saturated
one would report starvation as a scaling limit. 60 requests per point after 12
fixed warm-up requests, and the stack is rebuilt from scratch for every worker
count.

Only the service under test is scaled. The other four stay at one worker, so the
measurement moves one variable.

`child_processes` is read back from the OS for every run and recorded next to
the numbers. `--workers 8` that silently ran one process would produce a flat
curve and a confident wrong conclusion.

**What this is not.** Four physical cores run the load generator, the service
under test and the four services it may call. These are shapes, not capacities,
and eight workers on four cores is deliberately past the edge — the turnover is
the finding, not an accident to tune away.

## This was measured twice

The first run found the numbers below and traced them to the event store. The
store was then fixed ([ADR-012](adr/012-ship-the-event-store-fix.md)) and
everything re-measured. Both sets are kept, because the difference between them
is the result.

| endpoint | 1 worker before → after | best point before → after |
|---|---|---|
| `rag /v1/query` | 56.1 → **144.7** | 104.2 (4 workers) → **230.3** (8 workers) |
| `sales /v1/score` | 50.2 → **152.5** | 77.5 → **222.6** |
| `ops /v1/decide` | 46.3 → **59.0** | 46.3 → **89.2** |

Peak requests/second. The committed
[`scale-test.json`](assets/scale-test.json) holds the *after* run.

## Retrieval, before and after

`rag /v1/query`, CPU-bound in-process. Before the store was fixed:

| workers | peak req/s | p50 ms | p95 ms | speedup |
|---|---|---|---|---|
| 1 | 56.1 | 84.5 | 369.0 | 1.00 |
| 2 | 79.8 | 37.2 | 130.9 | 1.42 |
| **4** | **104.2** | 16.6 | 99.0 | **1.86** |
| 8 | 49.4 | 35.3 | 229.8 | 0.88 |

Four workers was the best point on every measure at once, and eight workers was
**worse than one**. After:

| workers | peak req/s | p50 ms | p95 ms | speedup |
|---|---|---|---|---|
| 1 | 144.7 | 94.9 | 118.0 | 1.00 |
| 2 | 138.0 | 36.0 | 144.1 | 0.95 |
| 4 | 215.2 | 11.2 | 42.8 | 1.49 |
| **8** | **230.3** | **10.7** | 50.2 | **1.59** |

The single-worker figure nearly tripled — with no cross-process contention at
all, which is the clearest evidence the cost was opening a connection rather
than waiting for one. And the collapse at eight workers is gone: it is now the
best point measured, so the earlier "four workers, then it falls over" reading
described the store rather than the cores.

`sales /v1/score` behaves the same way and remains the noisier curve: 152.5,
178.5, 222.6, 182.7. No single worker count is claimed as optimal for it.

## The fan-out endpoint, and an interpretation that was wrong

`ops /v1/decide` calls three other services, which stay at one worker while
`ops` is scaled. Before:

| workers | peak req/s | speedup |
|---|---|---|
| 1 | 46.3 | 1.00 |
| 2 | 34.6 | 0.75 |
| 4 | 30.8 | 0.67 |
| 8 | 27.4 | 0.59 |

Every added worker made it worse, and the obvious reading was the textbook one:
front-door capacity is not downstream capacity, so the extra processes compete
with the services they are waiting on. After the store was fixed:

| workers | peak req/s | speedup |
|---|---|---|
| 1 | 59.0 | 1.00 |
| 2 | 82.6 | 1.40 |
| 4 | 86.7 | 1.47 |
| 8 | 89.2 | 1.51 |

It scales. **The textbook reading was wrong here** — the downstream services
were store-bound, not capacity-bound, and the explanation was appealing enough
to have stopped the investigation. It is kept in this document rather than
quietly replaced, because a plausible architectural story that survives one
measurement and dies to the next is the more useful thing to have written down.

## The ceiling was the event store

Every request writes one event through `utils/storage.save_event`. The original
version opened a fresh connection per write, in SQLite's default
rollback-journal mode, re-running `CREATE TABLE IF NOT EXISTS` and
`CREATE INDEX IF NOT EXISTS` each time — invisible with one process, serialising
with several.

Suspecting is not measuring, so the store was measured on its own: no model, no
HTTP, no retrieval. Identical schema and identical `INSERT`, median of three
repeats, writes per second:

| processes | legacy (per-write) | + WAL only | shipped (reuse + WAL) | isolated files |
|---|---|---|---|---|
| 1 | 186.2 | 157.5 (0.85×) | **900.6 (4.84×)** | 861.8 |
| 2 | 172.9 | 77.0 (0.45×) | **881.3 (5.10×)** | 1626.4 |
| 4 | 168.5 | 116.3 (0.69×) | **848.0 (5.03×)** | 2776.4 |
| 8 | 168.3 | 141.3 (0.84×) | **893.6 (5.31×)** | 3200.3 |

`legacy` reproduces the old implementation so the comparison stays reproducible
rather than surviving in a commit message. `isolated` is one file per process —
the upper bound, not a proposal, since five services cannot each keep a private
copy of one event log and still have it be one.

Three things fall out:

**The old store did not scale at all.** Flat at 168–186 writes/second from one
process to eight, while isolated files scale 862 → 3200. Retrieval's 104.2 req/s
peak sat in the same band. The service could not outrun its own event log.

**Turning on WAL alone makes it worse** — 0.45× to 0.85× in every row. This was
the change that looked obvious before measuring. With a connection opened per
write, WAL's per-connection index setup and checkpointing cost more than the
rollback journal they replace, and none of the benefits apply. It is the change
a reviewer is most likely to suggest, and it is negative.

**The two only work together.** In an earlier prototype, connection reuse alone
measured about 2× and WAL alone was negative; together they were 8–9×. A change
that fails on its own measurement is most of the win once the access pattern is
fixed first.

## What shipped, and what it did not fix

The change landed in all five services
([ADR-012](adr/012-ship-the-event-store-fix.md)): one connection per thread,
opened once, WAL mode, keyed on the resolved `APP_DB_PATH` so repointing the
store opens a new connection rather than writing to the previous database.

**The store still does not scale with processes.** It is flat at ~870
writes/second whether one process writes or eight — writes to one file
serialise, and that has not changed. What changed is the height of the flat
line, from ~170 to ~870, which moved the constraint off the store and onto the
CPU. Endpoints now peak near 230 req/s, comfortably underneath it.

**The shipped path measures ~870 where the prototype measured ~1400.** The
difference is `_db_path()` rebuilding a `Path` from the environment on every
call to check the cached connection is still valid. That is the price of the
`APP_DB_PATH` safety; it is known, and not worth optimising while the store sits
four times above what the services ask of it.

**Absolute write rates are noisy.** The range across three repeats reaches
several hundred writes/second on the fastest strategies. The *ratios* held
across independent runs, and the ratios are what the table is for.

**Still one machine.** No second host, no network between services, no load
balancer, no soak. The event-store ceiling found here is the kind of thing that
transfers; the numbers are not.
