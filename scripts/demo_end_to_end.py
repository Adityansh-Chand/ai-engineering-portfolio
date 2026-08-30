"""End-to-end demo: five services, one system, one request id.

Six acts, in the order the story actually happens:

  1. A customer complains about checkout. Nothing is known to be wrong yet, so
     they get ordinary handling -- and the contact is remembered.
  2. Telemetry degrades until the incident platform opens an incident, and
     *pushes* an event.
  3. Operations acts on that event and reaches out to the customer from act 1
     unprompted. This is the only path in the system that starts without a
     customer asking, and it is what makes "proactive" literally true.
  4. A meeting decision is extracted, indexed into retrieval, and retrieved back.
  5. A new complaint about the degraded service becomes an incident response
     rather than an individual refund. The same complaint about a healthy
     service still gets an ordinary refund review.
  6. A dependency is killed. The decision is still made.

    python scripts/demo_end_to_end.py            # against docker compose
    python scripts/demo_end_to_end.py --local    # start the services here
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

PORTS = {"rag": 8001, "sales": 8002, "incident": 8003, "ops": 8004, "meeting": 8005}
REPOS = {
    "rag": "enterprise-rag-knowledge-system",
    "sales": "ai-sales-intelligence-engine",
    "incident": "ai-incident-detection-platform",
    "ops": "ai-proactive-customer-operations",
    "meeting": "autonomous-meeting-intelligence",
}
CUSTOMER = "acct_00001"


def url(service, path):
    return f"http://127.0.0.1:{PORTS[service]}{path}"


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


def wait_for(service, attempts=60):
    for _ in range(attempts):
        data, _ = call("GET", url(service, "/health"), timeout=5)
        if data:
            return True
        time.sleep(2)
    return False


def banner(text):
    print(f"\n{'=' * 76}\n{text}\n{'=' * 76}")


def start_local():
    base = {s: f"http://127.0.0.1:{p}" for s, p in PORTS.items()}
    env_for = {
        "rag": {"RETRIEVER": "bm25"},
        "sales": {},
        # The push edge: incident delivers events to operations.
        "incident": {"INCIDENT_MIN_ANOMALIES": "3", "EVENT_SUBSCRIBERS": base["ops"],
                     "EVENT_BACKOFF_SECONDS": "0.5"},
        "ops": {"SALES_API_URL": base["sales"], "INCIDENT_API_URL": base["incident"],
                "RAG_API_URL": base["rag"], "INTEGRATION_TIMEOUT_SECONDS": "3.0"},
        "meeting": {"RAG_API_URL": base["rag"]},
    }
    processes = []
    for service, repo in REPOS.items():
        path = WORKSPACE / repo
        if not path.exists():
            print(f"  missing repo: {path}")
            sys.exit(1)
        env = {**os.environ, **env_for[service],
               "APP_DB_PATH": str(path / "data" / "demo.sqlite3")}
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1",
             "--port", str(PORTS[service]), "--log-level", "warning"],
            cwd=str(path), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
        print(f"  starting {service:9s} on :{PORTS[service]}")
    return processes


def show_decision(decision):
    print(f"  intent    : {decision['intent']['label']} ({decision['intent']['confidence']})")
    print(f"  sentiment : {decision['sentiment']['label']}")
    for name, entry in decision["enrichment"].items():
        if not isinstance(entry, dict) or "outcome" not in entry:
            continue
        detail = ""
        data = entry.get("data") or {}
        if name == "account" and data:
            detail = f" segment={data.get('segment')}"
        elif name == "incident" and data:
            detail = f" active={data.get('active')}"
        elif name == "knowledge" and data:
            detail = f" top_source={data.get('top_source')}"
        print(f"  {name:9s} : {entry['outcome']}{detail}")
    print(f"  POLICY    : {decision['policy']['value']}  "
          f"(rule: {decision['policy']['rule']}, "
          f"enriched={decision['policy']['used_enrichment']})")
    print(f"  ACTION    : {decision['action']['type']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    processes = []
    if args.local:
        banner("Starting five services")
        processes = start_local()

    banner("Waiting for services")
    for service in REPOS:
        ok = wait_for(service)
        print(f"  {service:9s} {'ready' if ok else 'UNAVAILABLE'}")
        if not ok:
            print("\nA service did not come up. Is the stack running?")
            for process in processes:
                process.terminate()
            return 1

    request_id = f"demo-{uuid.uuid4().hex[:8]}"
    print(f"\nrequest id for this run: {request_id}")

    # ---- Act 1 ---------------------------------------------------------------
    banner("ACT 1  a customer complains -- nothing is known to be wrong yet")
    first, error = call("POST", url("ops", "/decide"), {
        "message": "my checkout payment keeps failing and I want my money back",
        "customer_id": CUSTOMER, "account_tier": "enterprise", "service": "checkout",
    }, request_id)
    if error:
        print(f"  decide failed: {error}")
    else:
        show_decision(first)
        print("\n  the contact is remembered, in case checkout turns out to be broken.")

    # ---- Act 2 ---------------------------------------------------------------
    banner("ACT 2  telemetry degrades -- the incident platform PUSHES an event")
    degraded = {"service": "checkout", "latency_ms": 640, "error_count": 19,
                "timeout_count": 6, "traffic_rpm": 1150,
                "cpu_percent": 79, "memory_percent": 71}
    for index in range(4):
        data, error = call("POST", url("incident", "/score"), degraded, request_id)
        if error:
            print(f"  scoring failed: {error}")
            break
        print(f"  minute {index + 1}: score={data['score']:.4f} anomaly={data['is_anomaly']}")

    health, _ = call("GET", url("incident", "/health"))
    if health:
        bus = health.get("event_bus", {})
        print(f"\n  event bus: subscribers={bus.get('subscribers')} "
              f"delivered={bus.get('delivered')} outbox={bus.get('outbox_depth')} "
              f"dlq={bus.get('dead_lettered')}")
        print(f"  delivery semantics: {bus.get('delivery')}")

    # ---- Act 3 ---------------------------------------------------------------
    banner("ACT 3  operations reaches out UNPROMPTED -- nobody asked for this")
    time.sleep(2)  # let the background delivery worker run
    outreach, error = call("GET", url("ops", "/proactive/outreach"), request_id=request_id)
    if error:
        print(f"  lookup failed: {error}")
    elif outreach and outreach.get("batches"):
        for batch in outreach["batches"]:
            print(f"  incident on {batch['service']} -> notified {batch['notified']} customer(s)")
            for item in batch["outreach"]:
                print(f"    {item['customer_id']}: {item['message']}")
        print(f"\n  audience: {outreach['batches'][0]['audience']}")
        print(f"  {outreach['status']['delivery']}")
    else:
        print("  no outreach yet (delivery may still be in flight)")

    # ---- Act 4 ---------------------------------------------------------------
    banner("ACT 4  a meeting decision becomes searchable knowledge")
    analysis, _ = call("POST", url("meeting", "/analyze"), {
        "transcript": ("Ravi: morning everyone.\n"
                       "Maya: we agreed to move forward with the checkout retry fix.\n"
                       "Priya will ship the checkout hotfix by Friday.\n"
                       "Arjun: no decision was made on pricing today."),
        "meeting_id": "demo_001", "title": "Checkout incident review",
    }, request_id)
    if analysis:
        print(f"  decisions    : {analysis['decisions']}")
        print(f"  action items : {[i['task'] for i in analysis['action_items']]}")
        print(f"  published    : {analysis['knowledge_publish']}")

    found, _ = call("GET", url("rag", "/query?q=checkout%20retry%20fix%20decision"),
                    request_id=request_id)
    if found:
        response = found["response"]
        top = response["sources"][0]["doc_id"] if response["sources"] else "-"
        print(f"\n  retrieval can now answer questions about that meeting:")
        print(f"  top source: {top}")

    # ---- Act 5 ---------------------------------------------------------------
    banner("ACT 5  the same complaint, with and without a known incident")
    again, _ = call("POST", url("ops", "/decide"), {
        "message": "my checkout payment keeps failing and I want my money back",
        "customer_id": CUSTOMER, "account_tier": "enterprise", "service": "checkout",
    }, request_id)
    if again:
        print("  -- checkout (incident active) --")
        show_decision(again)

    quiet, _ = call("POST", url("ops", "/decide"), {
        "message": "my identity login keeps failing and I want my money back",
        "customer_id": CUSTOMER, "account_tier": "enterprise", "service": "identity",
    }, request_id)
    if quiet:
        print("\n  -- identity (healthy) --")
        show_decision(quiet)
    print("\n  same words, different service, different decision.")

    # ---- Act 6 ---------------------------------------------------------------
    banner("ACT 6  a dependency dies -- the decision is still made")
    if args.local and processes:
        processes[list(REPOS).index("incident")].terminate()
        time.sleep(2)
        print("  incident service stopped\n")
        degraded_decision, error = call("POST", url("ops", "/decide"), {
            "message": "my checkout payment keeps failing and I want my money back",
            "customer_id": CUSTOMER, "account_tier": "enterprise", "service": "checkout",
        }, request_id)
        if error:
            print(f"  ops FAILED: {error}  <- this would be a bug")
        else:
            show_decision(degraded_decision)
            print(f"\n  incident enrichment: "
                  f"{degraded_decision['enrichment']['incident']['outcome']}")
            print("  the decision was still made.")
    else:
        print("  (run with --local to see this act)")

    banner("Done")
    print(f"Every call above carried request id {request_id}.")
    print("Grep any service's /events for it to see its side of the story.")

    for process in processes:
        process.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
