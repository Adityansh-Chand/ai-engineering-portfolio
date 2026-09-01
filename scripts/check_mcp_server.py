"""Connect a real MCP client to `agent/mcp_server.py` and check what it offers.

Starting the server proves nothing on its own -- a server that starts and
advertises the wrong tools looks identical from the outside. This runs an actual
client over stdio, completes the handshake, and asserts the advertised surface
against `agent/tools.py`, which is the registry both the MCP server and the
local agent read.

Two failures it is here to catch:

- **Drift.** A tool renamed or a description edited in `tools.py` while the MCP
  server still advertises the old one. Both sides read one registry, so this
  should be impossible; the check is what makes "should be" verifiable.
- **A silently changed prompt.** `describe_tools()` builds the text the local
  model sees, and the committed evaluation numbers are only valid for the exact
  prompt they were produced under. Adding schemas to the registry must not
  change that string, so the string is pinned here.

Needs no running services and no model: listing tools is a protocol operation,
not a call into them. `--live` additionally calls one tool, which does need the
stack up.

    python scripts/check_mcp_server.py
    python scripts/check_mcp_server.py --live
"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from tools import TOOLS, describe_tools, json_schema  # noqa: E402

# The exact tool listing the committed evaluation numbers were produced under.
# Pinned rather than regenerated: the point is to fail when it changes, and a
# fixture that rebuilds itself from the code cannot do that.
EXPECTED_PROMPT = """- knowledge_search(query): Search the internal knowledge base for documentation. Use for error codes such as ERR-4021, API reference such as POST /v2/invoices, settings such as retry.max_attempts, contract clauses, and any how-to or what-is question.
- account_score(customer_id): Get the renewal propensity score and segment for a known customer account id such as acct_00001.
- active_incidents(service): Check whether a named service -- checkout, payments, search, identity or billing -- is in an incident right now. Only for live status, never for looking up what an error code means.
- customer_decision(message, customer_id, service): Decide how to handle an inbound customer message: classify intent and return the policy and action to take.
- meeting_extract(transcript): Extract decisions and action items with owners from a meeting transcript supplied in the question.
- refuse(): no tool can answer this question"""

failures = []


def require(condition, message):
    if not condition:
        failures.append(message)


async def inspect_server(live):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "agent" / "mcp_server.py")],
        cwd=str(ROOT),
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            info = session.server_info
            print(f"connected: {info.name} v{info.version or '0'}"
                  f" (protocol {session.protocol_version})")

            listed = await session.list_tools()
            advertised = {tool.name: tool for tool in listed.tools}
            print(f"tools advertised: {', '.join(sorted(advertised))}")

            require(set(advertised) == set(TOOLS),
                    f"advertised {sorted(advertised)} but the registry has "
                    f"{sorted(TOOLS)}")

            for name, tool in TOOLS.items():
                served = advertised.get(name)
                if served is None:
                    continue
                require(served.description == tool["description"],
                        f"{name}: description differs from the registry")

                expected = json_schema(name)
                properties = (served.input_schema or {}).get("properties", {})
                require(set(properties) == set(expected["properties"]),
                        f"{name}: arguments {sorted(properties)} do not match "
                        f"{sorted(expected['properties'])}")
                required = set((served.input_schema or {}).get("required", []))
                require(required == set(expected["required"]),
                        f"{name}: required {sorted(required)} does not match "
                        f"{sorted(expected['required'])}")

            if live:
                result = await session.call_tool(
                    "active_incidents", {"service": "checkout"}
                )
                text = "".join(
                    block.text for block in result.content
                    if getattr(block, "type", None) == "text"
                )
                print(f"live call -> {text.strip()!r}")
                require(bool(text.strip()), "live call returned nothing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="also call a tool; needs the five services running")
    args = parser.parse_args()

    require(describe_tools() == EXPECTED_PROMPT,
            "describe_tools() no longer matches the prompt the committed "
            "evaluation numbers were measured under -- either restore it, or "
            "re-run agent/eval/run.py and update EXPECTED_PROMPT with the "
            "new results")

    asyncio.run(inspect_server(args.live))

    if failures:
        print(f"\n{len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print(f"\nMCP server is well-formed: {len(TOOLS)} tools, "
          f"descriptions and schemas match the registry, agent prompt unchanged")


if __name__ == "__main__":
    main()
