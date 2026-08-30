"""End-to-end demo: five services, one decision, one request id.

Tells the whole story in four acts:

  1. Telemetry degrades on `checkout` until the incident service opens an incident.
  2. A meeting records a decision; the meeting service indexes it into retrieval,
     so it becomes searchable knowledge.
  3. A customer complains about checkout. The operations service enriches its
     decision with account propensity (sales), incident status (incident), and a
     grounding passage (retrieval) -- then decides.
  4. The same customer, with no incident on their service, gets the ordinary
     decision -- showing enrichment changes outcomes rather than decorating them.

Then it kills the incident service and repeats act 3, to show the system degrades
instead of failing.

    # against docker compose
    python scripts/demo_end_to_end.py

    # against locally started services
    python scripts/demo_end_to_end.py --local
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

COMPOSE_PORTS = {"rag": 8001, "sales": 8002, "incident": 8003, "ops": 8004, "meeting": 8005}
LOCAL_PORTS = dict(COMPOSE_PORTS)

REPOS = {
    "rag": "enterprise-rag-knowledge-system",
    "sales": "ai-sales-intelligence-engine",
    "incident": "ai-incident-detection-platform",
    "ops": "ai-proactive-customer-operations",
    "meeting": "autonomous-meeting-intelligence",
}


def url(service, path, ports):
    return f"http://127.0.0.1:{ports[service]}{path}"


def call(method, target, payload=None, request_id=None, timeout=30):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if request_id:
        headers["X-Request-ID"] = request_id
    request = urllib.request.Request(target, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode()), None
    except urllib.error.HTTPError as error:
        return None, f"HTTP {error.code}"
    except Exception as error:  # noqa: BLE001 - demo surface
        return None, type(error).__name__


def wait_for(service, ports, attempts=60):
    for _ in range(attempts):
        data, _ = call("GET", url(service, "/health", ports), timeout=5)
        if data:
            return True
        time.sleep(2)
    return False


def banner(text):
    print(f"\n{'=' * 74}\n{text}\n{'=' * 74}")


def start_local():
    """Start all five services as subprocesses, wired to each other."""
    ports = LOCAL_PORTS
    base = {s: f"http://127.0.0.1:{p}" for s, p in ports.items()}
    processes = []

    env_for = {
        "rag": {"RETRIEVER": "bm25"},
        "sales": {},
        "incident": {"INCIDENT_MIN_ANOMALIES": "3"},
        "ops": {
            "SALES_API_URL": base["sales"],
            "INCIDENT_API_URL": base["incident"],
            "RAG_API_URL": base["rag"],
            "INTEGRATION_TIMEOUT_SECONDS": "3.0",
        },
        "meeting": {"RAG_API_URL": base["rag"]},
    }

    for service, repo in REPOS.items():
        path = WORKSPACE / repo
        if not path.exists():
            print(f"  missing repo: {path}")
            sys.exit(1)
        env = {**os.environ, **env_for[service], "APP_DB_PATH": str(path / "data" / "demo.sqlite3")}
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.server:app",
             "--host", "127.0.0.1", "--port", str(ports[service]), "--log-level", "warning"],
            cwd=str(path), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        print(f"  starting {service:9s} on :{ports[service]}")
    return processes, ports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true",
                        help="start the services as subprocesses instead of using compose")
    args = parser.parse_args()

    processes, ports = ([], COMPOSE_PORTS)
    if args.local:
        banner("Starting five services locally")
        processes, ports = start_local()

    banner("Waiting for services")
    for service in REPOS:
        ok = wait_for(service, ports)
        print(f"  {service:9s} {'ready' if ok else 'UNAVAILABLE'}")
        if not ok:
            print("\nA service did not come up. Is the stack running?")
            for process in processes:
                process.terminate()
            return 1

    request_id = f"demo-{uuid.uuid4().hex[:8]}"
    print(f"\nrequest id for this run: {request_id}")

    # ---- Act 1: an incident opens -------------------------------------------
    banner("ACT 1  telemetry degrades on checkout until an incident opens")
    degraded = {"service": "checkout", "latency_ms": 640, "error_count": 19,
                "timeout_count": 6, "traffic_rpm": 1150,
                "cpu_percent": 79, "memory_percent": 71}
    for index in range(4):
        data, error = call("POST", url("incident", "/score", ports), degraded, request_id)
        if error:
            print(f"  scoring failed: {error}")
            break
        print(f"  minute {index + 1}: score={data['score']:.4f} anomaly={data['is_anomaly']}")

    status, _ = call("GET", url("incident", "/incidents/active?service=checkout", ports),
                     request_id=request_id)
    print(f"\n  incident active: {status['active']}")
    if status.get("incident"):
        print(f"  {status['incident']['anomaly_count']} anomalous minutes, "
              f"peak score {status['incident']['peak_score']:.4f}")

    # ---- Act 2: a meeting becomes searchable knowledge -----------------------
    banner("ACT 2  a meeting decision becomes searchable knowledge")
    transcript = (
        "Ravi: morning everyone.\n"
        "Maya: we agreed to move forward with the checkout retry fix.\n"
        "Priya will ship the checkout hotfix by Friday.\n"
        "Arjun: no decision was made on pricing today."
    )
    analysis, error = call("POST", url("meeting", "/analyze", ports),
                           {"transcript": transcript, "meeting_id": "demo_001",
                            "title": "Checkout incident review"}, request_id)
    if analysis:
        print(f"  decisions found : {analysis['decisions']}")
        print(f"  action items    : {[i['task'] for i in analysis['action_items']]}")
        print(f"  published to rag: {analysis['knowledge_publish']}")

    print("\n  the retrieval service can now answer questions about that meeting:")
    found, _ = call("GET", url("rag", "/query?q=checkout%20retry%20fix%20decision", ports),
                    request_id=request_id)
    if found:
        response = found["response"]
        top = response["sources"][0]["doc_id"] if response["sources"] else "-"
        print(f"  top source: {top}")
        print(f"  answer    : {response['answer'][:150]}")

    # ---- Act 3: the enriched decision ---------------------------------------
    banner("ACT 3  a customer complains about checkout -- decision uses all three edges")
    complaint = {
        "message": "my checkout payment keeps failing and I want my money back",
        "customer_id": "acct_00001",
        "account_tier": "enterprise",
        "service": "checkout",
    }
    decision, error = call("POST", url("ops", "/decide", ports), complaint, request_id)
    if error:
        print(f"  decide failed: {error}")
    else:
        show_decision(decision)

    # ---- Act 4: same customer, no incident ----------------------------------
    banner("ACT 4  same complaint, a service with no incident -- ordinary handling")
    quiet = dict(complaint, service="identity",
                 message="my identity login keeps failing and I want my money back")
    decision, _ = call("POST", url("ops", "/decide", ports), quiet, request_id)
    if decision:
        show_decision(decision)

    # ---- Act 5: degradation --------------------------------------------------
    banner("ACT 5  the incident service goes away -- ops degrades, does not fail")
    if args.local and processes:
        processes[list(REPOS).index("incident")].terminate()
        time.sleep(2)
        print("  incident service stopped\n")
        decision, error = call("POST", url("ops", "/decide", ports), complaint, request_id)
        if error:
            print(f"  ops FAILED: {error}  <- this would be a bug")
        else:
            show_decision(decision)
            outcome = decision["enrichment"]["incident"]["outcome"]
            print(f"\n  incident enrichment outcome: {outcome}")
            print("  the decision was still made.")
    else:
        print("  (run with --local to see this act; it stops a container's process)")

    banner("Done")
    print(f"Every call above carried request id {request_id}.")
    print("Grep any service's /events for it to see its side of the story.")

    for process in processes:
        process.terminate()
    return 0


def show_decision(decision):
    print(f"  intent    : {decision['intent']['label']} ({decision['intent']['confidence']})")
    print(f"  sentiment : {decision['sentiment']['label']}")
    print(f"  priority  : {decision['priority']['value']}")
    for name, entry in decision["enrichment"].items():
        if not isinstance(entry, dict) or "outcome" not in entry:
            continue
        detail = ""
        if entry.get("data"):
            data = entry["data"]
            if name == "account":
                detail = f" segment={data.get('segment')} score={data.get('score')}"
            elif name == "incident":
                detail = f" active={data.get('active')}"
            elif name == "knowledge":
                detail = f" top_source={data.get('top_source')}"
        print(f"  {name:9s} : {entry['outcome']}{detail}")
    print(f"  POLICY    : {decision['policy']['value']}  "
          f"(rule: {decision['policy']['rule']}, "
          f"used_enrichment={decision['policy']['used_enrichment']})")
    print(f"  ACTION    : {decision['action']['type']}")


if __name__ == "__main__":
    sys.exit(main())
