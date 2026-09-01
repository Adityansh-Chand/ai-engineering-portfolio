# Load and degradation

Every other measurement in this portfolio is about quality: is the ranking right, is the
answer grounded, does the model beat its baseline. None of it says what happens when more
than one person uses the system at once, or when a dependency dies while they are using it.

Reproduce with:

```bash
python scripts/load_test.py
```

Raw numbers: [`assets/load-test.json`](assets/load-test.json).

---

## What this is not

The load generator and all five services run on **one laptop CPU**. Past modest concurrency
these numbers describe the machine, not the service. Each service runs a single uvicorn
worker, so a CPU-bound request holds the interpreter for its duration.

That makes this a **shape, not a capacity plan**. It is worth having anyway, because the
shape is what tells you where a system stops behaving linearly, and none of the following
would have been visible without measuring:

- three of these findings contradict what the median latency alone would have suggested
- one of them was a bug in the measurement, not the system, and is described below

The measurement itself needed two corrections before the numbers meant anything:

1. **Scenarios were contaminating each other.** Sharing one stack across scenarios showed
   retrieval as *slower at concurrency 1 than at concurrency 8*, which is not a thing a
   server does. The ops scenario leaves the incident service pushing events to ops with
   backoff, and the next scenario was measuring that. Each scenario now gets a fresh stack.
2. **Cold start was being reported as latency.** Warm-up scaled with the concurrency level,
   so the level-1 run was warmed by a single request and paid for lazy model loading across
   four services — 315 ms where the warm figure is 125 ms. Warm-up is now fixed at 12
   requests regardless of level.

Both were caught by a number looking impossible rather than by the harness complaining.

---

## Saturation

100 requests per level, after warm-up.

### `rag /v1/query` — retrieval, CPU-bound

| concurrency | p50 ms | p95 ms | p99 ms | req/s |
|---|---|---|---|---|
| 1 | 16.9 | 35.5 | 44.0 | 54.4 |
| 2 | 21.1 | 42.0 | 43.7 | 85.4 |
| 4 | 26.1 | 60.3 | 68.8 | 132.3 |
| 8 | 36.1 | 127.5 | 251.5 | 149.6 |
| 16 | 70.6 | 238.6 | 588.0 | 119.7 |
| **32** | 168.9 | 207.9 | 269.6 | **157.4** |

### `sales /v1/score` — model inference

| concurrency | p50 ms | p95 ms | p99 ms | req/s |
|---|---|---|---|---|
| 1 | 16.4 | 33.3 | 33.7 | 59.8 |
| 2 | 17.0 | 33.4 | 37.1 | 103.1 |
| 4 | 21.6 | 69.2 | 84.9 | 131.3 |
| **8** | 21.2 | 225.4 | 453.2 | **144.8** |
| 16 | 31.2 | 580.0 | 815.4 | 106.8 |
| 32 | 78.1 | 344.5 | 645.0 | 129.6 |

### `ops /v1/decide` — fans out to three services

| concurrency | p50 ms | p95 ms | p99 ms | req/s |
|---|---|---|---|---|
| 1 | 66.9 | 86.0 | 100.2 | 14.6 |
| 2 | 58.7 | 93.9 | 104.5 | 33.0 |
| 4 | 60.7 | 102.4 | 185.3 | 58.2 |
| 8 | 95.2 | 187.5 | 234.3 | 73.3 |
| 16 | 172.9 | 313.2 | 572.1 | 80.0 |
| **32** | 364.4 | 411.7 | 445.9 | **80.6** |

### Three findings, one of which replaced an earlier one

**Throughput no longer peaks and falls — and it used to.** The first run of this harness
found both CPU-bound endpoints topping out at concurrency 4 and getting *slower in
aggregate* beyond it: rag from 71.8 req/s down to 31.7. That was reported here as a finding
about the GIL and a single worker, and it was wrong. It was the event store, which capped
every endpoint near its own write rate
([ADR-012](adr/012-ship-the-event-store-fix.md)). With the store fixed, throughput rises
across the whole range tested and roughly doubles at every level.

Single-request latency changed too: rag's p50 at concurrency 1 went from 31.2 ms to 16.9 ms.
The old figure was a request waiting on a connection being opened and four schema statements
being re-run, not on retrieval.

**The median is still blind to saturation, but much less so.** At concurrency 16 rag's p50
is 70.6 ms against a p95 of 238.6 ms — a 3.4× spread. In the first run the same comparison
was 77.1 ms against **1490.1 ms**, nineteen times higher. The lesson survives the fix and
the severity does not: reporting p50 alone would still under-describe the tail, but the tail
is no longer catastrophic.

**The fan-out endpoint is the one that now saturates first.** `ops /v1/decide` flattens
around 80 req/s from concurrency 16 onward while the services it calls are still climbing —
it does three HTTP round trips per request, and that is now the dominant cost rather than
anything it computes. Its p50 at concurrency 2 (58.7 ms) is still *lower* than at
concurrency 1 (66.9 ms), because the second request uses the gap the first spends blocked.

**Caveat on p99:** at 100 samples per level, p99 is the second-slowest request. Treat it as
an indication of tail shape, not as a stable statistic. p95 is the tail figure worth reading.

---

## Degradation — killing a dependency under load

The claim this portfolio makes everywhere is that cross-service enrichment is *optional and
degrading*: a dead dependency may cost a decision its enrichment, but never the decision.
Unit tests assert that with a stubbed client, which proves the code path and not the
behaviour. Here the `sales` process is killed while `ops` is serving traffic.

| phase | p50 ms | p95 ms |
|---|---|---|
| healthy | 75.5 | 126.9 |
| dependency down, breaker still closed | 64.3 | **4185.1** |
| dependency down, breaker open | 47.9 | **74.6** |

**p95 falls from 4185 ms to 75 ms with the dependency still dead** — a 56× reduction, and
*below* the healthy figure, because a skipped call is faster than a successful one. Every
request returned 200 throughout.

That middle row is the reason the circuit breaker exists, and it is the row that would be
missing from a description of the design. While the breaker is closed, each request pays a
connection failure plus a retry before falling back — so the fallback works, and it is
expensive. The breaker's job is not to make failure survivable; the fallback already does
that. Its job is to stop paying full price for a failure that is not going to stop.

Note the p50 barely moves across all three phases: 85.9 → 81.8 → 94.2. **The entire effect
lives in the tail.** A median-only view of this incident would show nothing happening at all.

The degraded response says so in its own body, so a reader can tell an enrichment was
skipped rather than silently absent:

```json
{"account": "circuit_open", "incident": "ok", "knowledge": "ok"}
```

---

## What this does not cover

- **No horizontal scaling.** One worker per service, one machine. The obvious next step —
  more uvicorn workers — is untested here.
- **No sustained soak.** Each level runs for seconds, so nothing here would surface a leak,
  connection-pool exhaustion, or SQLite write contention over hours.
- **No network.** All calls are loopback. Real inter-service latency and packet loss are
  absent, which flatters the fan-out endpoint most.
- **Cold start is excluded by design.** First-request cost is real and is warmed away here
  deliberately, because mixing it into a latency distribution describes neither well.
