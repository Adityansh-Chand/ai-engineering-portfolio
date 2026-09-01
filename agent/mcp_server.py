"""The five services, exposed as an MCP server.

`agent/loop.py` drives these services with a hand-rolled JSON tool-call format,
invented here because a 0.5B model needed something it could actually emit. That
format is a private convention: nothing else can speak it, and a reviewer who
wanted to point their own client at these services would have to reimplement it.

The Model Context Protocol is the standard answer to that. Same five tools, same
`agent/tools.py` registry, same running services — but over a protocol any MCP
client can connect to, so the tools stop being an artifact of this repository's
agent and become an interface.

**Why this is not also the agent's transport.** The evaluation loop still calls
`tools.invoke` directly. Routing a local model's tool calls through an stdio
subprocess and a JSON-RPC round trip would add a process and some milliseconds
to buy nothing measurable — the model is generating at three tokens per second,
and the bottleneck is not the call. MCP earns its place by making the tools
reachable from outside, which is a different job from making them reachable from
inside, and conflating the two would be protocol for its own sake.

    python agent/mcp_server.py                  # stdio, for an MCP client
    python scripts/check_mcp_server.py          # verify it lists what it should

Configure a client (Claude Desktop, Claude Code, any MCP client) with:

    command: python
    args:    ["<path to>/agent/mcp_server.py"]

The five services must be running -- `python scripts/demo_end_to_end.py` or the
compose stack -- since every tool is an HTTP call to one of them.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "scripts"))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from tools import TOOLS, invoke  # noqa: E402

server = MCPServer(
    name="ai-engineering-portfolio",
    instructions=(
        "Tools over five independently running AI services: a retrieval "
        "knowledge base, account propensity scoring, live incident status, "
        "customer message triage, and meeting transcript extraction. Each tool "
        "is an HTTP call to a service that must already be running."
    ),
)


def _result(name, arguments):
    """Call the tool and return text, or a readable failure.

    A dead service is reported rather than raised. Every one of these tools
    reaches a separate process over HTTP, so "the service is down" is an
    ordinary outcome and the caller needs to be able to tell it apart from an
    empty answer -- the same contract the agent's tool-failure tasks measure.
    """
    result, error = invoke(name, arguments)
    if error:
        return f"{name} failed: {error}"
    return result["observation"]


@server.tool(name="knowledge_search", description=TOOLS["knowledge_search"]["description"])
def knowledge_search(query: str) -> str:
    return _result("knowledge_search", {"query": query})


@server.tool(name="account_score", description=TOOLS["account_score"]["description"])
def account_score(customer_id: str) -> str:
    return _result("account_score", {"customer_id": customer_id})


@server.tool(name="active_incidents", description=TOOLS["active_incidents"]["description"])
def active_incidents(service: str = "") -> str:
    return _result("active_incidents", {"service": service})


@server.tool(name="customer_decision", description=TOOLS["customer_decision"]["description"])
def customer_decision(message: str, customer_id: str = "acct_00001",
                      service: str = "checkout") -> str:
    return _result("customer_decision", {
        "message": message, "customer_id": customer_id, "service": service,
    })


@server.tool(name="meeting_extract", description=TOOLS["meeting_extract"]["description"])
def meeting_extract(transcript: str) -> str:
    return _result("meeting_extract", {"transcript": transcript})


if __name__ == "__main__":
    server.run(transport="stdio")
