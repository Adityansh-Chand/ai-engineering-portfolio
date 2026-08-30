"""Structural checks on the contract definitions.

Verifying contracts against live services needs all five repositories checked
out, which CI for this repo does not have. This checks the things that can rot
without that: malformed entries, unknown type names, references to services not
in the compose file, and contracts that verify nothing.
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALID_TYPES = {"string", "number", "boolean", "array", "object", "object_or_null"}
REPO_TO_SERVICE = {
    "enterprise-rag-knowledge-system": "rag",
    "ai-sales-intelligence-engine": "sales",
    "ai-incident-detection-platform": "incident",
    "ai-proactive-customer-operations": "ops",
    "autonomous-meeting-intelligence": "meeting",
}


def main():
    spec = json.loads((ROOT / "contracts" / "contracts.json").read_text(encoding="utf-8"))
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = set(compose.get("services", {}))

    errors = []
    seen_ids = set()

    for contract in spec["contracts"]:
        cid = contract.get("id")
        if not cid:
            errors.append("a contract has no id")
            continue
        if cid in seen_ids:
            errors.append(f"duplicate contract id '{cid}'")
        seen_ids.add(cid)

        for role in ("consumer", "provider"):
            repo = contract.get(role)
            if repo not in REPO_TO_SERVICE:
                errors.append(f"{cid}: unknown {role} repo '{repo}'")
            elif REPO_TO_SERVICE[repo] not in services:
                errors.append(f"{cid}: {role} '{repo}' is not in docker-compose.yml")

        request = contract.get("request") or {}
        if request.get("method") not in {"GET", "POST"}:
            errors.append(f"{cid}: unsupported method {request.get('method')!r}")
        if not str(request.get("path", "")).startswith("/"):
            errors.append(f"{cid}: path must start with '/'")

        fields = {
            **contract.get("required_fields", {}),
            **contract.get("optional_fields", {}),
        }
        if not fields:
            errors.append(f"{cid}: declares no fields, so it verifies nothing")
        for field, expected in fields.items():
            if expected not in VALID_TYPES:
                errors.append(f"{cid}: field '{field}' has unknown type '{expected}'")

        if not contract.get("why"):
            errors.append(f"{cid}: missing 'why' -- a contract without a reason rots")

    if errors:
        print("FAIL:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"OK: {len(spec['contracts'])} contract definitions well-formed")
    for contract in spec["contracts"]:
        pushes = contract.get("request", {}).get("target") == "consumer"
        arrow = "<-" if pushes else "->"
        print(f"  {contract['id']:34s} {contract['consumer']} {arrow} {contract['provider']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
