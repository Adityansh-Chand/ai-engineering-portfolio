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
| 1 | 31.2 | 35.0 | 36.8 | 36.5 |
| 2 | 31.6 | 45.5 | 64.0 | 62.4 |
| **4** | 44.1 | 119.2 | 137.5 | **71.8** |
| 8 | 63.7 | 343.8 | 721.4 | 66.3 |
| 16 | 77.1 | 1490.1 | 1928.2 | 49.1 |
| 32 | 179.4 | 2304.4 | 3028.5 | 31.7 |

### `sales /v1/score` — model inference

| concurrency | p50 ms | p95 ms | p99 ms | req/s |
|---|---|---|---|---|
| 1 | 30.9 | 32.7 | 48.0 | 36.2 |
| 2 | 31.6 | 43.9 | 58.6 | 64.9 |
| **4** | 41.2 | 97.5 | 125.6 | **77.4** |
| 8 | 49.2 | 311.0 | 1136.2 | 70.5 |
| 16 | 82.5 | 1051.4 | 1358.9 | 62.0 |
| 32 | 141.4 | 1573.0 | 1875.7 | 48.5 |

### `ops /v1/decide` — fans out to three services

| concurrency | p50 ms | p95 ms | p99 ms | req/s |
|---|---|---|---|---|
| 1 | 125.3 | 141.4 | 148.0 | 8.3 |
| 2 | 91.4 | 136.3 | 151.5 | 21.0 |
| 4 | 89.8 | 196.7 | 254.3 | 37.1 |
| **8** | 155.4 | 242.3 | 462.5 | **48.5** |
| 16 | 212.9 | 1521.1 | 2291.8 | 35.3 |
| 32 | 394.0 | 2154.1 | 2434.7 | 36.7 |

### Three findings

**Throughput peaks and then falls.** Both CPU-bound endpoints top out at concurrency 4 and
get *slower in aggregate* beyond it — rag from 71.8 req/s down to 31.7, sales from 77.4 to
48.5. Past the peak, additional load does not buy queued throughput; it costs throughput.
With one worker and a GIL that is expected, and it is the number that says "add workers
before you add anything else".

**The median is blind to saturation.** At concurrency 16, rag's p50 is 77.1 ms — a figure
that would pass any dashboard. Its p95 at the same moment is 1490.1 ms, nineteen times
higher. A service can look healthy at the median while one request in twenty takes a second
and a half. Reporting p50 alone here would have described a system that was not under strain.

**The fan-out endpoint tolerates more concurrency than the services it calls.** `ops` peaks
at 8 rather than 4, because it spends most of each request waiting on three HTTP calls
rather than computing. Its own CPU is mostly idle, which is exactly why its p50 at
concurrency 2 (91.4 ms) is *lower* than at concurrency 1 (125.3 ms) — the second request
uses the gap the first spends blocked.

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
| healthy | 85.9 | 145.3 |
| dependency down, breaker still closed | 81.8 | **4243.0** |
| dependency down, breaker open | 94.2 | **145.2** |

**p95 falls from 4243 ms to 145 ms with the dependency still dead** — a 29× reduction, back
to the healthy figure. Every request returned 200 throughout.

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
