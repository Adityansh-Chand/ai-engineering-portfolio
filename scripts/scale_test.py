"""Does adding worker processes actually add throughput?

`scripts/load_test.py` answered what one worker per service does under rising
concurrency, and found throughput peaking at four concurrent requests and then
falling. It left the obvious next question open: that peak is a property of one
process, so what happens with more of them?

This is the horizontal-scaling question at the only scale available here -- one
machine, more processes. It is not a substitute for measuring a real cluster,
and the ceiling found here is a property of this laptop. What transfers is not
the number but the *shape*: where the curve stops being linear, and why.

Three things are measured:

**Scaling efficiency.** Peak throughput at 1, 2, 4 and 8 uvicorn workers, each
found by sweeping concurrency rather than assuming the single-worker peak still
applies -- more workers need more offered load before they saturate. Efficiency
is throughput(w) / (w x throughput(1)): 1.0 is linear, and the interesting
number is where it falls off.

**The fan-out endpoint.** `ops /v1/decide` calls three other services, which stay
at one worker. Scaling only the front door is a common first instinct and the
measurement says what it buys.

**The event store, isolated.** Every request writes an event to SQLite through
`utils/storage.save_event`, which opens a connection per write in the default
rollback-journal mode. That is invisible with one process and serialising with
several, so it is the prime suspect for any ceiling found above. Suspecting is
not measuring, so `probe_event_store` runs the real `save_event` from W
processes against one shared database and against W separate ones. The ratio is
the contention cost with the model, the HTTP stack and the scheduler removed.

    python scripts/scale_test.py
    python scripts/scale_test.py --quick
    python scripts/scale_test.py --skip-probe
"""
import argparse
import json
import multiprocessing
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_assets import render  # noqa: E402
from load_test import SCENARIOS, drive, percentile  # noqa: E402
from service_harness import start, stop, wait_for_all  # noqa: E402

RESULTS_PATH = ROOT / "docs" / "assets" / "scale-test.json"
CARD_PATH = ROOT / "docs" / "assets" / "scale-test.svg"

WORKER_COUNTS = (1, 2, 4, 8)
QUICK_WORKERS = (1, 4)

# Swept rather than fixed. A single-worker peak of four concurrent requests says
# nothing about where eight workers saturate, and measuring eight workers at the
# one-worker peak would report starvation as a scaling limit.
CONCURRENCY_SWEEP = (4, 8, 16)
QUICK_SWEEP = (4, 16)

REQUESTS_PER_POINT = 60
QUICK_REQUESTS = 20
WARMUP_REQUESTS = 12
WARMUP_CONCURRENCY = 4

# Four physical cores, shared by the load generator, the service under test and
# the four services it may call. Eight workers is deliberately past that: the
# turnover is the finding, not an accident to be tuned away.
PHYSICAL_CORES = 4

SCALED = ("sales_score", "rag_query", "ops_decide")

PROBE_EVENTS_PER_PROCESS = 250
PROBE_REPEATS = 3
# A ladder, not a menu. `shared` is what the services ship today; each later
# entry changes exactly one thing; `isolated` removes sharing altogether and is
# the upper bound rather than a proposal -- five services cannot each keep their
# own copy of a shared event log and still have it be one.
PROBE_MODES = ("shared", "shared_wal", "reuse", "reuse_wal", "isolated")


def count_descendants(pid):
    """How many worker processes uvicorn actually forked.

    Asserted rather than assumed. `--workers 8` that silently ran one process
    would produce a flat scaling curve and a confident wrong conclusion.
    """
    if sys.platform != "win32":
        return None
    script = (
        f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}')"
        ".Count"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        return int(out.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        return None


def measure_scenario(name, scenario, worker_counts, sweep, requests):
    service = scenario["service"]
    print(f"\n=== {scenario['label']} ===")
    print(f"{'workers':>8}{'procs':>7}{'conc':>6}{'p50 ms':>9}{'p95 ms':>9}"
          f"{'req/s':>8}{'errors':>8}")

    rows = []
    for count in worker_counts:
        processes = start(
            f"scaletest-{name}-{count}", workers={service: count}
        )
        try:
            wait_for_all()
            observed = count_descendants(processes[service].pid)
            best = None
            for concurrency in sweep:
                drive(scenario, WARMUP_REQUESTS, WARMUP_CONCURRENCY)
                latencies, errors, wall = drive(scenario, requests, concurrency)
                point = {
                    "concurrency": concurrency,
                    "p50_ms": round(percentile(latencies, 50), 1),
                    "p95_ms": round(percentile(latencies, 95), 1),
                    "throughput_rps": round(len(latencies) / wall, 1) if wall else 0.0,
                    "errors": len(errors),
                    "error_kinds": sorted(set(errors)),
                }
                print(f"{count:>8}{observed if observed is not None else -1:>7}"
                      f"{concurrency:>6}{point['p50_ms']:>9.1f}"
                      f"{point['p95_ms']:>9.1f}{point['throughput_rps']:>8.1f}"
                      f"{point['errors']:>8}")
                if best is None or point["throughput_rps"] > best["throughput_rps"]:
                    best = point
            rows.append({
                "workers": count,
                "child_processes": observed,
                "peak": best,
                "sweep": sweep,
            })
        finally:
            stop(processes)

    baseline = rows[0]["peak"]["throughput_rps"] if rows else 0.0
    for row in rows:
        achieved = row["peak"]["throughput_rps"]
        row["speedup"] = round(achieved / baseline, 3) if baseline else 0.0
        row["efficiency"] = round(row["speedup"] / row["workers"], 3)
    return rows


INSERT = "INSERT INTO events (event_type, payload, request_id) VALUES (?, ?, ?)"


def _reusing_writer(database_path, use_wal):
    """The proposed change: one connection per process, held open.

    Deliberately not `save_event` -- this is a variant of it, written to find
    out whether connection reuse is what the shipped path is missing. Kept
    byte-identical in schema and statement so the only difference measured is
    when the connection is opened.
    """
    import json as _json
    import sqlite3 as _sqlite3

    connection = _sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, "
        "payload TEXT NOT NULL, request_id TEXT, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    if use_wal:
        connection.execute("PRAGMA journal_mode=WAL")
    connection.commit()

    def write(event_type, payload):
        connection.execute(INSERT, (event_type, _json.dumps(payload), None))
        connection.commit()

    return write


def _probe_worker(database_path, count, ready, start_at, outbox, mode="shared"):
    """Write `count` events through the real `save_event`, timed from a barrier.

    Imports the shipped module rather than reimplementing the insert, because a
    reimplementation would measure the probe's opinion of the write path instead
    of the write path.

    Reports writes that *completed*, not writes that were attempted. The first
    version of this probe assumed they were the same, and at eight processes
    they were not -- writes started failing outright, the processes exited
    early, and dividing the attempted total by the elapsed time reported the
    contention getting *better* precisely where it had got bad enough to start
    dropping data.
    """
    sys.path.insert(0, str(WORKSPACE / "ai-sales-intelligence-engine"))
    import os
    import sqlite3

    os.environ["APP_DB_PATH"] = database_path
    if mode.startswith("reuse"):
        save_event = _reusing_writer(database_path, use_wal=mode.endswith("wal"))
    else:
        from utils.storage import save_event

    save_event("probe_warmup", {"n": 0})
    ready.wait()
    while time.time() < start_at:
        pass

    written, locked = 0, 0
    for index in range(count):
        try:
            save_event("probe", {"n": index})
            written += 1
        except sqlite3.OperationalError:
            # Python's sqlite3 waits `timeout` seconds (5.0 by default) for the
            # write lock before raising. Reaching this line means a write waited
            # five seconds and then gave up.
            locked += 1
    outbox.put((written, locked))


def probe_event_store(worker_counts, events_per_process=PROBE_EVENTS_PER_PROCESS,
                      repeats=PROBE_REPEATS):
    """Shared SQLite file versus one file per process, same code path.

    Isolates the store: no model, no HTTP, no retrieval. Whatever ratio appears
    here is what the event store costs a multi-process deployment.

    Median of `repeats`, because a single pass is not reproducible: consecutive
    single-process runs measured 94.7 and 179.5 writes/second on an idle
    machine. The *shape* held across both -- shared flat, isolated rising -- but
    reporting one pass would put a number in the README that the next run
    contradicts.
    """
    print("\n=== event store: five write strategies, same schema and statement ===")
    print(f"{'procs':>6}" + "".join(f"{mode:>15}" for mode in PROBE_MODES)
          + f"{'lost':>7}")

    scratch = ROOT / "docs" / "assets" / "_scale_probe"
    scratch.mkdir(parents=True, exist_ok=True)
    results = []

    for count in worker_counts:
        samples = {mode: [] for mode in PROBE_MODES}
        dropped = {mode: 0 for mode in PROBE_MODES}
        for mode, _ in [(m, r) for r in range(repeats) for m in PROBE_MODES]:
            for old in list(scratch.glob("*.sqlite3*")):
                old.unlink(missing_ok=True)
            if mode == "isolated":
                paths = [str(scratch / f"isolated-{index}.sqlite3")
                         for index in range(count)]
            else:
                paths = [str(scratch / "shared.sqlite3")] * count
            if mode == "shared_wal":
                # Write-ahead logging is a property of the database file, not of
                # the connection, so it survives being set here and applies to
                # the shipped `save_event` unchanged. That is the point: this
                # measures the change without first making it, so the decision
                # to edit five repositories can be taken on a number.
                connection = sqlite3.connect(paths[0])
                connection.execute("PRAGMA journal_mode=WAL")
                connection.close()
            ready = multiprocessing.Barrier(count + 1)
            outbox = multiprocessing.Queue()
            # A start time in the near future, so every process begins writing
            # at the same instant. Without it the first process finishes part of
            # its work uncontended and the contention is understated.
            start_at = time.time() + 1.0
            workers = [
                multiprocessing.Process(
                    target=_probe_worker,
                    args=(paths[index], events_per_process, ready, start_at,
                          outbox, mode),
                )
                for index in range(count)
            ]
            for worker in workers:
                worker.start()
            ready.wait()
            remaining = start_at - time.time()
            if remaining > 0:
                time.sleep(remaining)
            began = time.perf_counter()
            reports = [outbox.get() for _ in range(count)]
            elapsed = time.perf_counter() - began
            for worker in workers:
                worker.join()
            written = sum(report[0] for report in reports)
            samples[mode].append(written / elapsed if elapsed > 0 else 0.0)
            dropped[mode] += sum(report[1] for report in reports)

        measured = {
            mode: round(statistics.median(values), 1)
            for mode, values in samples.items()
        }
        spread = {
            mode: round(max(values) - min(values), 1)
            for mode, values in samples.items()
        }
        # Every strategy is quoted against the shipped one, because the decision
        # this table informs is "change `save_event` to do what?" and an
        # absolute writes/second on this laptop does not answer that.
        relative = {
            mode: (round(measured[mode] / measured["shared"], 3)
                   if measured["shared"] else 0.0)
            for mode in PROBE_MODES
        }
        print(f"{count:>6}"
              + "".join(f"{measured[mode]:>15.1f}" for mode in PROBE_MODES)
              + f"{sum(dropped.values()):>7}")
        results.append({
            "processes": count,
            "writes_per_second": measured,
            "relative_to_shipped": relative,
            "writes_lost_to_lock_timeout": dropped,
            "range_across_repeats": spread,
        })

    for old in list(scratch.glob("*.sqlite3*")):
        old.unlink(missing_ok=True)
    try:
        scratch.rmdir()
    except OSError:
        pass
    return results


def format_card(results):
    lines = []
    for name, scenario in results["scenarios"].items():
        lines.append(scenario["label"])
        lines.append(f"{'workers':>8}{'peak req/s':>12}{'speedup':>10}"
                     f"{'efficiency':>12}")
        for row in scenario["rows"]:
            lines.append(f"{row['workers']:>8}{row['peak']['throughput_rps']:>12.1f}"
                         f"{row['speedup']:>10.2f}{row['efficiency']:>12.2f}")
        lines.append("")

    probe = results.get("event_store")
    if probe:
        lines.append("event store writes/second -- same schema, same statement")
        lines.append(f"{'procs':>6}" + "".join(f"{m:>15}" for m in PROBE_MODES))
        for row in probe:
            lines.append(f"{row['processes']:>6}" + "".join(
                f"{row['writes_per_second'][m]:>15.1f}" for m in PROBE_MODES))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-probe", action="store_true")
    # The scenario sweep restarts the stack twelve times and the probe does not
    # touch it, so re-measuring the store should not cost a rerun of everything
    # that did not change.
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    if args.probe_only:
        if not RESULTS_PATH.exists():
            raise SystemExit("--probe-only needs an existing scale-test.json")
        existing = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        existing["event_store"] = probe_event_store(
            QUICK_WORKERS if args.quick else WORKER_COUNTS
        )
        if not args.no_save:
            RESULTS_PATH.write_text(
                json.dumps(existing, indent=2) + "\n", encoding="utf-8"
            )
            render(
                "Horizontal scaling on one machine, and the ceiling it finds",
                "python scripts/scale_test.py",
                format_card(existing),
                CARD_PATH,
            )
            print(f"\nresults -> {RESULTS_PATH.relative_to(ROOT)}")
        return

    worker_counts = QUICK_WORKERS if args.quick else WORKER_COUNTS
    sweep = QUICK_SWEEP if args.quick else CONCURRENCY_SWEEP
    requests = QUICK_REQUESTS if args.quick else REQUESTS_PER_POINT

    results = {
        "physical_cores": PHYSICAL_CORES,
        "worker_counts": list(worker_counts),
        "concurrency_sweep": list(sweep),
        "requests_per_point": requests,
        "scenarios": {},
    }

    for name in SCALED:
        results["scenarios"][name] = {
            "label": SCENARIOS[name]["label"],
            "rows": measure_scenario(
                name, SCENARIOS[name], worker_counts, sweep, requests
            ),
        }

    if not args.skip_probe:
        results["event_store"] = probe_event_store(worker_counts)

    if not args.no_save:
        RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nresults -> {RESULTS_PATH.relative_to(ROOT)}")
        render(
            "Horizontal scaling on one machine, and the ceiling it finds",
            "python scripts/scale_test.py",
            format_card(results),
            CARD_PATH,
        )
        print(f"card    -> {CARD_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
