"""Measure what the stack does under concurrency, and what happens when a
dependency dies underneath it.

Everything else in this portfolio measures quality: is the ranking right, is the
answer grounded, does the model beat its baseline. None of it says what happens
when more than one person uses the system at once, which is the first question
anyone operating it would ask.

Two things are measured here:

**Saturation.** Latency percentiles and throughput at rising concurrency, per
endpoint, including the fan-out endpoint that calls three other services to
answer one request. The interesting number is where p95 stops tracking p50 --
that is the point where requests start queueing rather than running.

**Degradation.** A dependency is killed mid-run. The claim this portfolio makes
everywhere is that enrichment is optional and degrading: a dead dependency must
cost a decision nothing. That is asserted by unit tests with a stubbed client,
which proves the code path and not the behaviour under load. Here the process is
actually killed while traffic is flowing, and what the circuit breaker does to
tail latency is measured rather than described.

**What this is not.** The load generator and all five services share one laptop
CPU. Past modest concurrency the numbers describe the machine, not the service,
and they are reported as such -- see `docs/LOAD_TEST.md`. A number produced this
way is a shape, not a capacity plan.

    python scripts/load_test.py                  # full run, writes results
    python scripts/load_test.py --quick          # fewer levels, shorter
    python scripts/load_test.py --skip-breaker
"""
import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_assets import render  # noqa: E402
from service_harness import base, call, start, stop, wait_for_all  # noqa: E402

RESULTS_PATH = ROOT / "docs" / "assets" / "load-test.json"
CARD_PATH = ROOT / "docs" / "assets" / "load-test.svg"

CONCURRENCY_LEVELS = (1, 2, 4, 8, 16, 32)
QUICK_LEVELS = (1, 4, 16)
REQUESTS_PER_LEVEL = 100
QUICK_REQUESTS = 20

# Fixed, not scaled to the concurrency level. Scaling it meant the level-1 run
# was warmed by exactly one request, so it paid for lazy model loading and index
# construction across four services and reported 315 ms where the warm figure is
# under 40 -- a startup cost printed as a latency characteristic.
WARMUP_REQUESTS = 12
WARMUP_CONCURRENCY = 4

# One scenario per shape of work: a fan-out that calls three services, a
# retrieval query that is CPU-bound in-process, and a model inference.
SCENARIOS = {
    "ops_decide": {
        "label": "ops /v1/decide (fans out to sales, incident, rag)",
        "service": "ops",
        "method": "POST",
        "path": "/v1/decide",
        "payload": {
            "message": "checkout keeps failing at payment and I am losing orders",
            "customer_id": "acct_00001",
            "account_tier": "enterprise",
            "service": "checkout",
        },
    },
    "rag_query": {
        "label": "rag /v1/query (retrieval, CPU-bound)",
        "service": "rag",
        "method": "GET",
        "path": "/v1/query?q=ERR-4021%20remediation%20steps",
        "payload": None,
    },
    "sales_score": {
        "label": "sales /v1/score (model inference)",
        "service": "sales",
        "method": "POST",
        "path": "/v1/score",
        "payload": {
            "account_id": "acct_00001",
            "visits": 24,
            "spend": 4200.0,
            "account_age_days": 540,
            "usage_frequency": 0.65,
            "support_tickets": 3,
            "renewal_days": 45,
        },
    },
}


def percentile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (q / 100.0) * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def drive(scenario, count, concurrency, timeout=30):
    """Issue `count` requests across `concurrency` threads. Returns latencies+errors."""
    url = base(scenario["service"]) + scenario["path"]
    pending = list(range(count))
    lock = threading.Lock()
    latencies, errors = [], []

    def worker():
        while True:
            with lock:
                if not pending:
                    return
                pending.pop()
            started = time.perf_counter()
            _, error = call(
                scenario["method"], url, payload=scenario["payload"], timeout=timeout
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            with lock:
                latencies.append(elapsed_ms)
                if error:
                    errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    wall_start = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - wall_start

    return latencies, errors, wall


def measure_scenario(name, scenario, levels, requests):
    print(f"\n=== {scenario['label']} ===")
    print(f"{'conc':>5}{'n':>6}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}"
          f"{'req/s':>9}{'errors':>8}")
    rows = []
    for concurrency in levels:
        drive(scenario, WARMUP_REQUESTS, WARMUP_CONCURRENCY)

        latencies, errors, wall = drive(scenario, requests, concurrency)
        row = {
            "concurrency": concurrency,
            "requests": len(latencies),
            "p50_ms": round(percentile(latencies, 50), 1),
            "p95_ms": round(percentile(latencies, 95), 1),
            "p99_ms": round(percentile(latencies, 99), 1),
            "mean_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
            "throughput_rps": round(len(latencies) / wall, 1) if wall else 0.0,
            "errors": len(errors),
            "error_kinds": sorted(set(errors)),
        }
        rows.append(row)
        print(f"{concurrency:>5}{row['requests']:>6}{row['p50_ms']:>10.1f}"
              f"{row['p95_ms']:>10.1f}{row['p99_ms']:>10.1f}"
              f"{row['throughput_rps']:>9.1f}{row['errors']:>8}")
    return rows


def measure_breaker(processes, requests=120, concurrency=4):
    """Kill `sales` mid-run and watch what the circuit breaker does to latency.

    Reported in three phases rather than as one average, because the average is
    the one number that hides the entire effect.
    """
    scenario = SCENARIOS["ops_decide"]
    print("\n=== circuit breaker: killing `sales` while ops is under load ===")

    drive(scenario, WARMUP_REQUESTS, WARMUP_CONCURRENCY)
    healthy_latencies, _, _ = drive(scenario, requests // 3, concurrency)

    processes["sales"].kill()
    processes["sales"].wait(timeout=10)

    # Immediately after the kill the breaker is still closed, so every request
    # pays a full connection failure or timeout before falling back.
    failing_latencies, _, _ = drive(scenario, requests // 3, concurrency)
    # By now repeated failures have opened it, and the call is skipped outright.
    open_latencies, open_errors, _ = drive(scenario, requests // 3, concurrency)

    sample, sample_error = call(
        "POST", base("ops") + scenario["path"], payload=scenario["payload"], timeout=30
    )

    phases = {
        "healthy": healthy_latencies,
        "dependency_down_breaker_closed": failing_latencies,
        "dependency_down_breaker_open": open_latencies,
    }
    result = {
        phase: {
            "p50_ms": round(percentile(values, 50), 1),
            "p95_ms": round(percentile(values, 95), 1),
        }
        for phase, values in phases.items()
    }
    result["requests_still_succeeded"] = sample_error is None
    result["failed_request_count_while_open"] = len(open_errors)
    if sample:
        result["degraded_response_records_the_reason"] = _enrichment_outcomes(sample)

    print(f"{'phase':<38}{'p50 ms':>10}{'p95 ms':>10}")
    for phase in phases:
        print(f"{phase:<38}{result[phase]['p50_ms']:>10.1f}"
              f"{result[phase]['p95_ms']:>10.1f}")
    print(f"\nrequests still returned 200 with the dependency dead: "
          f"{result['requests_still_succeeded']}")
    if "degraded_response_records_the_reason" in result:
        print(f"enrichment outcomes recorded in the response: "
              f"{result['degraded_response_records_the_reason']}")
    return result


def _enrichment_outcomes(response):
    """Pull the per-enrichment outcome codes out of whatever shape the trace has.

    The point being checked is that a reader of the response alone can tell an
    enrichment was skipped rather than silently absent.
    """
    outcomes = {}
    for key, value in (response.get("enrichment") or response).items():
        if isinstance(value, dict) and "outcome" in value:
            outcomes[key] = value["outcome"]
        elif isinstance(value, str) and value in (
            "ok", "not_configured", "timeout", "circuit_open", "error"
        ):
            outcomes[key] = value
    return outcomes


def format_card(results):
    """The two findings worth a picture, in the terminal format the other cards use."""
    lines = []
    for name, scenario in results["scenarios"].items():
        lines.append(scenario["label"])
        lines.append(f"{'conc':>5}{'p50 ms':>10}{'p95 ms':>10}{'req/s':>9}")
        for row in scenario["rows"]:
            lines.append(
                f"{row['concurrency']:>5}{row['p50_ms']:>10.1f}"
                f"{row['p95_ms']:>10.1f}{row['throughput_rps']:>9.1f}"
            )
        lines.append("")

    breaker = results.get("circuit_breaker")
    if breaker:
        lines.append("circuit breaker -- `sales` killed while ops is under load")
        lines.append(f"{'phase':<38}{'p50 ms':>10}{'p95 ms':>10}")
        for phase in ("healthy", "dependency_down_breaker_closed",
                      "dependency_down_breaker_open"):
            lines.append(f"{phase:<38}{breaker[phase]['p50_ms']:>10.1f}"
                         f"{breaker[phase]['p95_ms']:>10.1f}")
        lines.append("")
        lines.append(f"requests still returned 200: "
                     f"{breaker['requests_still_succeeded']}")
        outcomes = breaker.get("degraded_response_records_the_reason", {})
        if outcomes:
            lines.append(f"enrichment outcomes in the response: {outcomes}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-breaker", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    levels = QUICK_LEVELS if args.quick else CONCURRENCY_LEVELS
    requests = QUICK_REQUESTS if args.quick else REQUESTS_PER_LEVEL

    results = {
        "levels": list(levels),
        "requests_per_level": requests,
        "scenarios": {},
    }

    # A fresh stack per scenario. Sharing one stack looked cheaper and produced
    # nonsense: the ops scenario leaves the incident service pushing events to
    # ops with backoff, and the next scenario then measured that instead. It
    # showed as retrieval being *slower* at concurrency 1 than at 8, which is
    # not a thing a server does -- a clear sign the load generator was measuring
    # itself rather than the service.
    for name, scenario in SCENARIOS.items():
        processes = start(f"loadtest-{name}")
        try:
            wait_for_all()
            results["scenarios"][name] = {
                "label": scenario["label"],
                "rows": measure_scenario(name, scenario, levels, requests),
            }
        finally:
            stop(processes)

    if not args.skip_breaker:
        processes = start("loadtest-breaker")
        try:
            wait_for_all()
            results["circuit_breaker"] = measure_breaker(processes)
        finally:
            stop(processes)

    if not args.no_save:
        RESULTS_PATH.write_text(
            json.dumps(results, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nresults -> {RESULTS_PATH.relative_to(ROOT)}")
        render(
            "Concurrency and degradation, measured on one laptop CPU",
            "python scripts/load_test.py",
            format_card(results),
            CARD_PATH,
        )
        print(f"card    -> {CARD_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
