"""Start the five services as local processes, wait for health, stop them.

Extracted so the run report and the load test drive the stack the same way. They
had started as one copy each of this logic, which is exactly how two harnesses
end up disagreeing about what "the stack" means -- one with a fresh event store
and one without, and a trace that quietly counts hops from a previous run.

Ports are non-default on purpose: these processes are meant to coexist with a
`docker compose up` on 8001-8005 without either noticing the other.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

KEY = "portfolio-demo-key"
PORTS = {"rag": 8821, "sales": 8822, "incident": 8823, "ops": 8824, "meeting": 8825}
REPOS = {
    "rag": "enterprise-rag-knowledge-system",
    "sales": "ai-sales-intelligence-engine",
    "incident": "ai-incident-detection-platform",
    "ops": "ai-proactive-customer-operations",
    "meeting": "autonomous-meeting-intelligence",
}


def base(service):
    return f"http://127.0.0.1:{PORTS[service]}"


def call(method, url, payload=None, request_id=None, timeout=40):
    """Returns (data, error). Never raises -- callers here treat failure as data."""
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-API-Key": KEY}
    if request_id:
        headers["X-Request-ID"] = request_id
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode()), None
    except urllib.error.HTTPError as error:
        return None, f"HTTP {error.code}"
    except Exception as error:  # noqa: BLE001
        return None, type(error).__name__


def environment_for(name):
    return {
        "rag": {"RETRIEVER": "bm25"},
        "sales": {},
        "incident": {"INCIDENT_MIN_ANOMALIES": "3", "EVENT_SUBSCRIBERS": base("ops"),
                     "EVENT_BACKOFF_SECONDS": "0.5"},
        "ops": {"SALES_API_URL": base("sales"), "INCIDENT_API_URL": base("incident"),
                "RAG_API_URL": base("rag"), "INTEGRATION_TIMEOUT_SECONDS": "3.0"},
        "meeting": {"RAG_API_URL": base("rag")},
    }[name]


def start(store_name, services=None, overrides=None, workers=None):
    """Launch the services and return {name: Popen}.

    `store_name` names a per-run SQLite file that is deleted first. Without a
    fresh store a second run appends to the first, and any count read back from
    the event log describes two runs rather than one.

    `workers` is `{service: count}` for the horizontal-scaling test. Only the
    service under test is scaled; the rest stay at one, so the measurement moves
    one variable. Above one worker uvicorn forks children, which is why `stop`
    has to kill a tree rather than a process.
    """
    processes = {}
    for service in services or REPOS:
        path = WORKSPACE / REPOS[service]
        if not path.exists():
            raise SystemExit(f"missing repository: {path}")

        database = path / "data" / f"{store_name}.sqlite3"
        database.parent.mkdir(parents=True, exist_ok=True)
        # The store runs in WAL mode, so committed events can be sitting in the
        # `-wal` sidecar rather than the database file. Deleting only the
        # database would leave them to be recovered on the next open, which is
        # the stale-store bug this delete exists to prevent, arriving through a
        # file the delete did not know about.
        for suffix in ("", "-wal", "-shm"):
            database.with_name(database.name + suffix).unlink(missing_ok=True)

        env = {
            **os.environ,
            **environment_for(service),
            **(overrides or {}).get(service, {}),
            "API_KEY": KEY,
            "INTEGRATION_API_KEY": KEY,
            "APP_DB_PATH": str(database),
        }
        command = [
            sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1",
            "--port", str(PORTS[service]), "--log-level", "warning",
        ]
        count = (workers or {}).get(service, 1)
        if count > 1:
            command += ["--workers", str(count)]
        processes[service] = subprocess.Popen(
            command, cwd=str(path), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    return processes


def kill_tree(process):
    """Kill a service and any workers it forked.

    `Popen.terminate()` signals only the process we launched. With `--workers`
    that is the supervisor, and its children survive, keep the port bound, and
    the next run then measures a stack it did not start -- the same class of bug
    as a shared event store, arriving through process management instead.
    """
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        process.terminate()


def wait_for_all(services=None):
    for service in services or REPOS:
        for _ in range(60):
            data, _ = call("GET", base(service) + "/health", timeout=5)
            if data:
                break
            time.sleep(2)
        else:
            raise SystemExit(f"{service} never became healthy")


def stop(processes):
    items = list(processes.values()) if isinstance(processes, dict) else list(processes)
    for process in items:
        kill_tree(process)
    for process in items:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
