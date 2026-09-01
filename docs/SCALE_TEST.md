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

## Retrieval scales to the core count, then falls over

`rag /v1/query`, CPU-bound in-process:

| workers | peak req/s | at concurrency | p50 ms | p95 ms | speedup | efficiency |
|---|---|---|---|---|---|---|
| 1 | 56.1 | 8 | 84.5 | 369.0 | 1.00 | 1.00 |
| 2 | 79.8 | 4 | 37.2 | 130.9 | 1.42 | 0.71 |
| **4** | **104.2** | 4 | **16.6** | **99.0** | **1.86** | 0.46 |
| 8 | 49.4 | 4 | 35.3 | 229.8 | 0.88 | 0.11 |

Four workers is the best point on every measure at once: highest throughput,
lowest p50, lowest p95. Eight workers is **worse than one** — 0.88× — because
there are four cores and eight processes contending for them.

Efficiency never reaches 1.0 even at two workers (0.71). Some of that is the
load generator and the four idle services sharing the same CPU. The rest is the
subject of the last section.

`sales /v1/score` does not give a clean curve: 50.2, 64.2, 59.0, 77.5 req/s at 1,
2, 4 and 8 workers. It is fast enough that measurement noise is comparable to
the effect, and **no worker count is claimed as optimal for it**. Reporting the
retrieval curve as if it generalised to every endpoint would be reading a shape
into noise.

## Scaling the front door makes the fan-out slower

`ops /v1/decide` calls three other services to answer one request. Those stay at
one worker while `ops` is scaled:

| workers | peak req/s | p50 ms | p95 ms | speedup |
|---|---|---|---|---|
| 1 | 46.3 | 159.0 | 261.5 | 1.00 |
| 2 | 34.6 | 204.5 | 319.0 | 0.75 |
| 4 | 30.8 | 267.8 | 600.0 | 0.67 |
| 8 | 27.4 | 228.1 | 442.5 | 0.59 |

Every added worker made it worse. This is the expected result and it is worth
having measured: adding capacity at the front door does not add capacity
downstream, and on a fixed core budget the extra front-door processes compete
with the very services they are waiting on. The queue moved; it did not shorten.

## The ceiling is the event store

Retrieval peaks at **104.2 req/s**. Every request writes one event through
`utils/storage.save_event`, which opens a fresh connection per write, in
SQLite's default rollback-journal mode, re-running `CREATE TABLE IF NOT EXISTS`
and `CREATE INDEX IF NOT EXISTS` each time. That is invisible with one process
and serialising with several.

Suspecting is not measuring, so the store was measured on its own — no model, no
HTTP, no retrieval. Five write strategies, identical schema and identical
`INSERT`, median of three repeats:

| processes | shipped | + WAL only | + reuse only | reuse + WAL | isolated files |
|---|---|---|---|---|---|
| 1 | 194.6 | 107.7 (0.55×) | 351.2 (1.81×) | 1602.0 (8.23×) | 170.9 |
| 2 | 168.5 | 134.6 (0.80×) | 356.0 (2.11×) | 1391.1 (8.26×) | 352.5 |
| 4 | 116.0 | 67.3 (0.58×) | 247.1 (2.13×) | **1100.2 (9.48×)** | 406.9 |
| 8 | 109.3 | 87.8 (0.80×) | 254.1 (2.33×) | 969.1 (8.87×) | 467.4 |

Writes per second. `isolated` is one file per process — the upper bound, not a
proposal, since five services cannot each keep a private copy of a shared event
log and still have it be one.

Three things fall out:

**The shipped store does not scale at all.** 194.6 writes/second at one process,
116.0 at four. It gets *slower* as processes are added, while isolated files
scale 170.9 → 406.9. And the retrieval endpoint's 104.2 req/s peak sits in the
same band as the store's 116.0 writes/second at the same process count. The
service cannot outrun its own event log.

**Turning on WAL alone makes it worse** — 0.55× to 0.80× in every row. This was
the change that looked obvious before measuring. With a connection opened per
write, WAL's per-connection index setup and checkpointing cost more than the
rollback journal it replaces, and none of its benefits apply.

**The two changes only work together.** Connection reuse alone is about 2×. WAL
alone is negative. Both together are **8.2–9.5×**, consistently, at every
process count. A change that would have been rejected on its own measurement is
most of the win once the access pattern is fixed first.

## What was not done, and why

**The fix is not shipped.** It is a change to `utils/storage.py` in five
repositories, and a held-open connection is not the same object as a
per-call one: `uvicorn` serves on a thread pool, so it needs
`check_same_thread=False` and a lock, and it must re-open when `APP_DB_PATH`
changes or every test that points the store at a temporary file will silently
write to the previous one. That is a real change with real hazards, and it is
scoped as work rather than slipped in behind a measurement.
See [`docs/adr/009`](adr/009-event-store-is-the-scaling-ceiling.md).

**Absolute write rates are noisy.** The range across three repeats reaches 512
writes/second on the fastest strategy. The *ratios* are stable across
independent runs — reuse+WAL measured 8.2–9.5× here and 8.2–9.5× in a separate
earlier run — and the ratios are what the table is for.

**Still one machine.** No second host, no network between services, no load
balancer, no soak. The event-store ceiling found here is the kind of thing that
transfers; the numbers are not.
