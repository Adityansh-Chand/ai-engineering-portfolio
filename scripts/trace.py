"""Reconstruct one request's path across all five services.

The request id already travels across every service boundary -- `utils/security.py`
accepts an inbound `X-Request-ID` or mints one, and each service forwards it on
the calls it makes. Until now nothing collected it, so following a single decision
meant querying five `/v1/events` endpoints by hand and joining the answers by eye.

This is that collector. It is a script rather than a service on purpose: at five
services on one host, a tracing backend would be more operational surface than the
problem justifies. The portfolio README records that reasoning under "Out of scope
by decision"; what was genuinely missing was the join, not the infrastructure.

    python scripts/trace.py <request-id>            # against docker compose
    python scripts/trace.py <request-id> --demo     # after a --local demo run

Ports match docker-compose.yml. Override with --base to point elsewhere.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

PORTS = {"rag": 8001, "sales": 8002, "incident": 8003, "ops": 8004, "meeting": 8005}

# Which service a hop belongs to is obvious from the port, but the event type is
# what tells a reader what actually happened, so it is kept verbatim.
API = "/v1"
DEFAULT_KEY = "portfolio-demo-key"


def fetch(base, service, request_id, api_key, limit):
    query = urllib.parse.urlencode({"request_id": request_id, "limit": limit})
    url = f"{base[service]}{API}/events?{query}"
    request = urllib.request.Request(url, headers={"X-API-Key": api_key})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode()).get("events", []), None
    except urllib.error.HTTPError as error:
        return [], f"HTTP {error.code}"
    except Exception as error:  # noqa: BLE001 - a down service is a normal answer
        return [], type(error).__name__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request_id")
    parser.add_argument("--base", default="http://127.0.0.1",
                        help="host serving the five services")
    parser.add_argument("--api-key", default=DEFAULT_KEY)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--json", action="store_true",
                        help="emit the joined timeline as JSON")
    args = parser.parse_args()

    base = {service: f"{args.base}:{port}" for service, port in PORTS.items()}

    timeline, unreachable = [], {}
    for service in PORTS:
        events, error = fetch(base, service, args.request_id, args.api_key, args.limit)
        if error:
            unreachable[service] = error
            continue
        for event in events:
            timeline.append({
                "service": service,
                "event_type": event.get("event_type"),
                "created_at": event.get("created_at"),
                "payload": event.get("payload"),
            })

    # created_at is a SQLite CURRENT_TIMESTAMP string, so it sorts correctly as
    # text. Sorting by service would hide the thing worth seeing: the order.
    timeline.sort(key=lambda hop: (hop["created_at"] or "", hop["service"]))

    if args.json:
        print(json.dumps({"request_id": args.request_id, "hops": timeline,
                          "unreachable": unreachable}, indent=2))
        return 0

    print(f"\nrequest id: {args.request_id}")
    print("=" * 78)
    if not timeline:
        print("no events found for that request id.")
        print("\nlikely causes:")
        print("  - the id is wrong (the demo prints the one it used)")
        print("  - the services are not running, or are on different ports")
        print("  - the request predates request-id storage")
        if unreachable:
            print(f"\nunreachable: {unreachable}")
        return 1

    for index, hop in enumerate(timeline, start=1):
        print(f"{index:2d}. {hop['created_at']}  {hop['service']:9s} "
              f"{hop['event_type']}")
        payload = hop["payload"] or {}
        for key in ("policy", "action", "intent", "sentiment", "score", "segment",
                    "service", "query", "doc_id", "notified", "duplicate",
                    "retrieval_score", "groundedness", "anomaly"):
            if key in payload:
                value = payload[key]
                if isinstance(value, dict):
                    value = value.get("value", value.get("label", value))
                print(f"      {key:16s} {str(value)[:60]}")

    print("=" * 78)
    services = sorted({hop["service"] for hop in timeline})
    print(f"{len(timeline)} hop(s) across {len(services)} service(s): "
          f"{', '.join(services)}")
    if unreachable:
        # A service that is down is reported rather than silently omitted: an
        # incomplete trace that looks complete is worse than no trace.
        print(f"could not reach: {unreachable}")
        print("the timeline above is therefore INCOMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
