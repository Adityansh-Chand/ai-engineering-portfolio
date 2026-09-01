# ADR-013 — Expose the services over MCP, but do not route the agent through it

**Status:** Accepted · **Date:** 2026-09

## Context

`agent/loop.py` drives the five services with a tool-call format invented here:
a JSON object with `tool` and `arguments`, parsed by a brace-matching scanner in
this repository. It exists because a 0.5B model needed something it could
reliably emit, and it works — 0.0360 invalid-call rate at 1.5B.

It is also a private convention. Nothing outside this repository can speak it,
so the five services are reachable by exactly one client: the one written here.
A reviewer who wanted to point their own tooling at them would have to
reimplement the format first, which is a strange thing to require of an
interface whose whole claim is that the services are independently usable.

The Model Context Protocol is the standard answer, and it is not hypothetical
here — it is the protocol used in production at work to connect models to tools.
The portfolio inventing its own instead is the gap.

## Decision

**Expose the five tools as an MCP server. Leave the evaluation loop calling them
directly.**

`agent/mcp_server.py` serves the same five tools over stdio, reading
`agent/tools.py` — the same registry the local agent's prompt is built from — so
descriptions cannot diverge. Any MCP client can connect.

The agent's own tool calls still go through `tools.invoke`.

## Alternatives considered

**Route the agent's tool calls through MCP too.** The tidy answer, and the one
that would make a better sentence. Rejected on measurement: the model generates
at roughly three tokens per second, so a tool call's cost is dominated by
generating it, not by dispatching it. Adding a subprocess, a JSON-RPC round trip
and an async client to a path whose latency is invisible next to the model would
be protocol adopted for its own sake. MCP earns its place by making the tools
reachable **from outside**, which is a different job from making them reachable
from inside.

It would also have a cost worth naming: the committed evaluation numbers are
valid for one exact prompt, and re-plumbing the call path risks changing it. A
2.4-hour re-run to prove a null result is a poor trade.

**Replace the hand-rolled format with MCP's tool-call shape in the prompt.**
Rejected for the same reason and one more: the format is a *finding*. The
evaluation reports an invalid-call rate precisely because a small model's
ability to emit structured calls is one of the things being measured. Swapping
in a different shape mid-stream would discard the comparison between 0.5B and
1.5B on the format they were both measured against.

**Write the MCP schemas by hand alongside the prompt descriptions.** Faster to
write, and it is two descriptions of one tool. They drift the first time an
argument is renamed. `json_schema()` derives the MCP `inputSchema` from the same
`parameters` and `required` entries the prompt is built from, and
`scripts/check_mcp_server.py` connects a real client and asserts the advertised
surface matches the registry.

**Expose it over HTTP rather than stdio.** Streamable HTTP is supported by the
SDK and is the right choice for a hosted server. Rejected as the default here
because the tools are already HTTP services — a second HTTP layer in front of
them adds a port to manage and a process to keep alive for a portfolio that runs
on one laptop. stdio is what a local MCP client expects and needs no lifecycle.

## Consequences

- **The five services are now usable by any MCP client** — Claude Desktop,
  Claude Code, anything else — without this repository's agent. That is the
  point: the tools stop being an artifact of one evaluation harness.
- **One registry, two consumers.** `agent/tools.py` feeds both the local agent's
  prompt and the MCP server's schemas. CI asserts they agree, and asserts the
  prompt string itself is unchanged, because the committed evaluation numbers
  are only valid for the exact prompt that produced them.
- **A new dependency**, `mcp>=2.0,<3.0`, declared in `agent/requirements.txt`.
  The pin is not cosmetic: 2.0 renamed `FastMCP` to `MCPServer` and moved the
  `Tool` model to snake_case fields, so 1.x code does not run.
- The verification needs no running services and no model, so it runs in CI —
  unlike the evaluation itself, which needs both.
- **The agent's tool-call format stays non-standard**, and that is now a stated
  choice rather than an omission.

## Revisit when

The agent runs on a model large enough that dispatch latency is a measurable
share of a tool call, or something other than this repository's harness needs to
drive the agent loop. Either makes routing through MCP a real question rather
than a cosmetic one.
