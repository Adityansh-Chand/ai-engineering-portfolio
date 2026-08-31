"""Validate the multi-service compose file's structure and integration wiring.

Build contexts point at sibling repositories that are not checked out in CI, so
this checks the things that actually rot -- service names, port collisions, and
whether the integration edges still point at services that exist -- rather than
building images. Each service's own CI builds its image.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"rag", "sales", "incident", "ops", "meeting"}
EXPECTED_EDGES = {
    "ops": {"SALES_API_URL": "sales", "INCIDENT_API_URL": "incident", "RAG_API_URL": "rag"},
    "meeting": {"RAG_API_URL": "rag"},
}


def main():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose.get("services", {})
    errors = []

    missing = EXPECTED - set(services)
    if missing:
        errors.append(f"missing services: {sorted(missing)}")

    seen_ports = {}
    for name, spec in services.items():
        for mapping in spec.get("ports", []):
            host = str(mapping).split(":")[0]
            if host in seen_ports:
                errors.append(f"port {host} claimed by both {seen_ports[host]} and {name}")
            seen_ports[host] = name

    for name, edges in EXPECTED_EDGES.items():
        env = services.get(name, {}).get("environment", {}) or {}
        for var, target in edges.items():
            value = env.get(var)
            if not value:
                errors.append(f"{name} is missing {var}")
            elif target not in str(value):
                errors.append(f"{name}.{var}={value} does not point at '{target}'")
            if target not in services:
                errors.append(f"{name}.{var} targets unknown service '{target}'")

    for name in EXPECTED_EDGES:
        for target in set(EXPECTED_EDGES[name].values()):
            depends = services.get(name, {}).get("depends_on", {}) or {}
            if target not in depends:
                errors.append(f"{name} should depend_on {target}")

    # Every service needs both halves: API_KEY to demand a key from its callers,
    # INTEGRATION_API_KEY to send one to its dependencies. Setting only one is
    # worse than setting neither -- the service refuses callers, or gets refused.
    #
    # This check exists because its absence is exactly how the stack shipped with
    # authentication switched off: `require_api_key` returns immediately when
    # API_KEY is unset, so every endpoint looked protected, passed its tests, and
    # served anyone. An auth check that never runs cannot be distinguished from a
    # broken one, so the wiring is asserted here rather than assumed.
    for name in sorted(EXPECTED & set(services)):
        env = services[name].get("environment", {}) or {}
        for var in ("API_KEY", "INTEGRATION_API_KEY"):
            if not env.get(var):
                errors.append(f"{name} is missing {var} -- auth would be off")

    if errors:
        print("FAIL:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"OK: {len(services)} services, wiring consistent, auth on for all")
    for name, edges in EXPECTED_EDGES.items():
        print(f"  {name} -> {', '.join(sorted(set(edges.values())))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
