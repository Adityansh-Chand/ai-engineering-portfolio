# ADR-008 — Model cost and measure load locally instead of deploying

**Status:** Accepted · **Date:** 2026-08

## Context

Two gaps were named honestly in the portfolio's own status section: no load testing, and no
cost model. Both are things an architecture argument is incomplete without — a design that
never mentions what it costs or what it does under concurrency has not been argued, only
described.

The obvious way to close them is to deploy: stand the stack up on a cloud provider, drive
real traffic, read the bill. That costs money, and this portfolio is explicitly not funded.

The question was whether the gaps could be closed with evidence rather than assertion at
zero spend, or whether "we would need to deploy" was the honest answer.

## Decision

Close both gaps locally, and be exact about which half of each is measured.

**Load:** `scripts/load_test.py` drives the real stack at rising concurrency, reports p50 /
p95 / p99 and throughput per endpoint, and **kills a dependency mid-run** to measure what
the circuit breaker actually does. All measured.

**Cost:** `scripts/cost_model.py` derives cost per million requests from that measured
throughput and from dated unit prices in `scripts/pricing.json`, each citing the page it was
read from. Throughput measured, prices sourced, arithmetic computed — nothing estimated.

The rule: **measured where measurable, modelled where not, and never mixed up.**

## Alternatives considered

**Deploy to a cloud free tier and measure for real.** The strongest evidence, and rejected
on the user's explicit constraint that nothing may cost money — free tiers expire, exceed
quietly, and require a card on file. A conditional charge is still a charge.

**Estimate latency from first principles instead of measuring.** Rejected. An estimate of
how fast the code "should" be is not evidence, and it would have been wrong: the measurement
found that throughput on both CPU-bound endpoints *peaks at concurrency 4 and then falls*,
which no reasoning-from-the-architecture would have produced.

**Publish the price table as findings.** Rejected as the failure mode this whole exercise
invites. Prices are dated inputs with sources, not claims — the artifact is the model and
the sensitivity analysis, and the doc says so at the top.

**Leave both gaps open and keep saying so.** The status quo, and honest. Rejected because
the gaps were closeable at zero cost, and "we did not measure" stops being an acceptable
answer once measuring is free.

## Consequences

- **The cost model contradicts what the load test implies.** The saturation curve makes
  concurrency look like the thing to optimise; the sensitivity analysis shows doubling
  retrieval throughput changes the bill by 0.009% while changing model tier changes it by
  400%. Neither measurement says that alone. Recorded because the load test on its own
  points at the wrong problem.
- The compute figures inherit a laptop CPU, and cost per request is derived from throughput.
  The structure transfers; the absolute compute numbers would need re-measuring on the
  target instance. Token costs do not have this problem — they are hardware-free.
- Prices go stale. `pricing.json` carries an `as_of` date and source URLs so staleness is
  visible rather than silent, but nothing automatically re-checks them.
- Building the harness surfaced two measurement bugs before it produced any number:
  scenarios contaminating each other through a background event-delivery loop, and cold
  start being reported as latency. Both were caught by a figure looking impossible —
  retrieval "slower at concurrency 1 than at 8" — rather than by anything failing.
- What remains genuinely absent is stated rather than approximated: no horizontal scaling,
  no soak test, no network, no idle-cost modelling below the crossover, and no bill.

## Revisit when

There is a reason to deploy that is not "to produce a number" — a real user, or a
requirement that cannot be checked locally. At that point these artifacts become the
baseline to compare the deployment against, which is more useful than either would have been
alone.
