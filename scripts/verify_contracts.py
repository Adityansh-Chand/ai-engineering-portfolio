"""Verify the consumer-driven contracts against live services.

The failure this exists to prevent: a provider changes a response field, its own
tests still pass because nothing in that repo reads the field, and the consumer
breaks at runtime in a way no test suite catches. With five services and five
edges, that is the most likely way this system rots.

Each contract in `contracts/contracts.json` records what a consumer **actually
reads** from a provider. Fields not listed are not depended on and providers may
change them freely -- which is the useful half of writing them down.

    python scripts/verify_contracts.py            # against docker compose
    python scripts/verify_contracts.py --local    # start the services first
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
CONTRACTS = ROOT / "contracts" / "contracts.json"

PORTS = {"rag": 8001, "sales": 8002, "incident": 8003, "ops": 8004, "meeting": 8005}
REPO_TO_SERVICE = {
    "enterprise-rag-knowledge-system": "rag",
    "ai-sales-intelligence-engine": "sales",
    "ai-incident-detection-platform": "incident",
    "ai-proactive-customer-operations": "ops",
    "autonomous-meeting-intelligence": "meeting",
}

TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "object_or_null": lambda v: v is None or isinstance(v, dict),
}


def resolve(payload, dotted):
    """Read a dotted path such as `response.answer`, or raise KeyError."""
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted)
        current = current[part]
    return current


def call(method, url, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def wait_for(service, attempts=60):
    for _ in range(attempts):
        try:
            call("GET", f"http://127.0.0.1:{PORTS[service]}/health", timeout=5)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return False


def start_local():
    base = {s: f"http://127.0.0.1:{p}" for s, p in PORTS.items()}
    env_for = {
        "rag": {"RETRIEVER": "bm25"},
        "sales": {},
        "incident": {"EVENT_SUBSCRIBERS": base["ops"]},
        "ops": {"SALES_API_URL": base["sales"], "INCIDENT_API_URL": base["incident"],
                "RAG_API_URL": base["rag"]},
        "meeting": {"RAG_API_URL": base["rag"]},
    }
    processes = []
    for repo, service in REPO_TO_SERVICE.items():
        path = WORKSPACE / repo
        if not path.exists():
            print(f"missing repo: {path}")
            sys.exit(1)
        env = {**os.environ, **env_for[service],
               "APP_DB_PATH": str(path / "data" / "contracts.sqlite3")}
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1",
             "--port", str(PORTS[service]), "--log-level", "warning"],
            cwd=str(path), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ))
    return processes


def target_service(contract):
    """Which service is actually called: usually the provider, unless it pushes."""
    role = contract.get("request", {}).get("target", "provider")
    repo = contract[role if role == "consumer" else "provider"]
    return REPO_TO_SERVICE[repo]


def verify(contract):
    request = contract["request"]
    service = target_service(contract)
    path = request["path"]

    if "{account_id}" in path:
        # Ask the provider for an id it actually holds rather than inventing one.
        health = call("GET", f"http://127.0.0.1:{PORTS['sales']}/health")
        examples = health.get("example_account_ids") or []
        if not examples:
            return False, ["sales exposes no example_account_ids to probe with"]
        path = path.replace("{account_id}", examples[0])

    url = f"http://127.0.0.1:{PORTS[service]}{path}"
    if request.get("query"):
        url = f"{url}?{urllib.parse.urlencode(request['query'])}"

    try:
        payload = call(request["method"], url, request.get("body"))
    except urllib.error.HTTPError as error:
        return False, [f"HTTP {error.code} from {url}"]
    except Exception as error:  # noqa: BLE001
        return False, [f"{type(error).__name__} calling {url}"]

    failures = []
    for field, expected in {**contract.get("required_fields", {}),
                            **contract.get("optional_fields", {})}.items():
        optional = field in contract.get("optional_fields", {})
        try:
            value = resolve(payload, field)
        except KeyError:
            if not optional:
                failures.append(f"missing field '{field}'")
            continue
        check = TYPE_CHECKS.get(expected)
        if check and not check(value):
            failures.append(
                f"field '{field}' expected {expected}, got {type(value).__name__}"
            )
    return not failures, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    spec = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    contracts = spec["contracts"]

    processes = []
    if args.local:
        print("starting services ...")
        processes = start_local()

    for service in PORTS:
        if not wait_for(service):
            print(f"FAIL: {service} did not come up")
            for process in processes:
                process.terminate()
            return 1

    print(f"\nverifying {len(contracts)} consumer-driven contracts\n")
    failed = 0
    for contract in contracts:
        ok, failures = verify(contract)
        arrow = "<-" if contract.get("request", {}).get("target") == "consumer" else "->"
        label = f"{contract['consumer'].split('-')[-1]} {arrow} {contract['provider'].split('-')[-1]}"
        print(f"  {'PASS' if ok else 'FAIL'}  {contract['id']:34s} ({label})")
        for failure in failures:
            print(f"          {failure}")
        failed += 0 if ok else 1

    print()
    if failed:
        print(f"{failed} of {len(contracts)} contracts FAILED")
        print("A provider changed a field a consumer reads. Fix the provider, or")
        print("update the contract and the consumer together.")
    else:
        print(f"all {len(contracts)} contracts hold")

    for process in processes:
        process.terminate()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
