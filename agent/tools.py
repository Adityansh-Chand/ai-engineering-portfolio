"""The five services, described as tools a language model can choose between.

This is the whole reason the agent lives in this repository rather than in a
sixth one: the tools are the services that already exist, unchanged. Nothing was
added to them to make them agent-friendly, and nothing here reaches past their
public API. If the agent can drive them, so can anything else.

**Observations are deliberately small.** The model generates at roughly three
tokens per second, so every token of tool output is paid for twice -- once to
read it and again in the answer that follows. Each tool returns a compact line
rather than the service's full JSON, and the raw payload is kept alongside for
the evaluation harness to score against. A model that had to read a 900-token
response before answering would spend its entire budget on prefill.
"""
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from service_harness import base, call  # noqa: E402

# The two names the loop understands that are not services. `refuse` is a
# first-class option rather than a fallback: a question no tool can answer is a
# case to be handled, and the evaluation set contains it on purpose.
ANSWER = "answer"
REFUSE = "refuse"


def _knowledge_search(arguments):
    query = str(arguments.get("query", "")).strip()
    if not query:
        return None, "query is required"
    url = base("rag") + "/v1/query?q=" + urllib.parse.quote(query)
    data, error = call("GET", url, timeout=30)
    if error:
        return None, error
    response = data.get("response", data)
    return {
        "observation": (
            f"answer: {response.get('answer', '')}\n"
            f"retrieval_score: {response.get('retrieval_score', 0)}"
        ),
        "raw": response,
    }, None


def _account_score(arguments):
    customer_id = str(arguments.get("customer_id", "")).strip()
    if not customer_id:
        return None, "customer_id is required"
    url = base("sales") + f"/v1/accounts/{urllib.parse.quote(customer_id)}/score"
    data, error = call("GET", url, timeout=30)
    if error:
        return None, error
    return {
        "observation": (
            f"account {customer_id}: score {data.get('score')}, "
            f"segment {data.get('segment')}"
        ),
        "raw": data,
    }, None


def _active_incidents(arguments):
    service = str(arguments.get("service", "")).strip()
    url = base("incident") + "/v1/incidents/active"
    if service:
        url += "?service=" + urllib.parse.quote(service)
    data, error = call("GET", url, timeout=30)
    if error:
        return None, error
    if service:
        state = "yes" if data.get("active") else "no"
        return {
            "observation": f"incident active on {service}: {state}",
            "raw": data,
        }, None
    return {
        "observation": f"active incidents: {data.get('active_count', 0)}",
        "raw": data,
    }, None


def _customer_decision(arguments):
    message = str(arguments.get("message", "")).strip()
    if not message:
        return None, "message is required"
    payload = {
        "message": message,
        "customer_id": str(arguments.get("customer_id", "acct_00001")),
        "account_tier": str(arguments.get("account_tier", "standard")),
        "service": str(arguments.get("service", "checkout")),
    }
    data, error = call("POST", base("ops") + "/v1/decide", payload=payload, timeout=40)
    if error:
        return None, error
    intent = (data.get("intent") or {}).get("label")
    return {
        "observation": (
            f"intent: {intent}, policy: {data.get('policy')}, "
            f"action: {data.get('action')}"
        ),
        "raw": data,
    }, None


def _meeting_extract(arguments):
    transcript = str(arguments.get("transcript", "")).strip()
    if not transcript:
        return None, "transcript is required"
    payload = {"meeting_id": "agent-query", "transcript": transcript}
    data, error = call(
        "POST", base("meeting") + "/v1/analyze", payload=payload, timeout=40
    )
    if error:
        return None, error
    decisions = data.get("decisions") or []
    actions = data.get("action_items") or []
    return {
        "observation": (
            f"decisions: {len(decisions)}, action_items: {len(actions)}\n"
            + "\n".join(f"- {item_text(item)}" for item in (decisions + actions)[:4])
        ),
        "raw": data,
    }, None


def item_text(item):
    """Decisions come back as strings and action items as dicts.

    Two shapes because they are two things: a decision is a sentence, an action
    item is a sentence plus an owner and a due date. Assuming one shape for both
    was an `AttributeError` on `str.get` that the tool layer swallowed into a
    bare failure, so the task scored zero for a reason that had nothing to do
    with the model.
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("task", "text", "source_text"):
            if item.get(key):
                return str(item[key])
    return str(item)


TOOLS = {
    # Descriptions were revised once, after watching the model send every
    # `ERR-####` question to `active_incidents` -- it reads "ERR" as "incident".
    # The fix belongs here rather than in the task set: a tool whose description
    # does not distinguish it from its neighbour is a tool definition problem,
    # and naming the identifier shapes is what a real deployment would do. The
    # revision is disclosed in `docs/AGENT.md` because it happened after seeing
    # results, which is the kind of iteration that quietly inflates a score.
    "knowledge_search": {
        "service": "rag",
        "description": (
            "Search the internal knowledge base for documentation. Use for "
            "error codes such as ERR-4021, API reference such as POST "
            "/v2/invoices, settings such as retry.max_attempts, contract "
            "clauses, and any how-to or what-is question."
        ),
        "parameters": {"query": "the search text"},
        "invoke": _knowledge_search,
    },
    "account_score": {
        "service": "sales",
        "description": (
            "Get the renewal propensity score and segment for a known customer "
            "account id such as acct_00001."
        ),
        "parameters": {"customer_id": "the account id"},
        "invoke": _account_score,
    },
    "active_incidents": {
        "service": "incident",
        "description": (
            "Check whether a named service -- checkout, payments, search, "
            "identity or billing -- is in an incident right now. Only for live "
            "status, never for looking up what an error code means."
        ),
        "parameters": {"service": "service name, or empty for all"},
        "invoke": _active_incidents,
    },
    "customer_decision": {
        "service": "ops",
        "description": (
            "Decide how to handle an inbound customer message: classify intent "
            "and return the policy and action to take."
        ),
        "parameters": {
            "message": "the customer's message",
            "customer_id": "the account id",
            "service": "the service they mention",
        },
        "invoke": _customer_decision,
    },
    "meeting_extract": {
        "service": "meeting",
        "description": (
            "Extract decisions and action items with owners from a meeting "
            "transcript supplied in the question."
        ),
        "parameters": {"transcript": "the transcript text"},
        "invoke": _meeting_extract,
    },
}


def describe_tools():
    """The tool list as the model sees it.

    Kept terse for the same reason observations are: this text is re-read on
    every step of every task, so a verbose schema is paid for on every call.
    """
    lines = []
    for name, tool in TOOLS.items():
        arguments = ", ".join(tool["parameters"])
        lines.append(f"- {name}({arguments}): {tool['description']}")
    lines.append(f"- {REFUSE}(): no tool can answer this question")
    return "\n".join(lines)


def invoke(name, arguments):
    """Returns (result, error). `result` has `observation` and `raw`."""
    tool = TOOLS.get(name)
    if tool is None:
        return None, f"unknown tool {name}"
    try:
        return tool["invoke"](arguments or {})
    except Exception as error:  # noqa: BLE001
        return None, type(error).__name__
