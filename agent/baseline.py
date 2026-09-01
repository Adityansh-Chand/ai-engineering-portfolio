"""The same job, routed by keywords instead of by a model.

Every learned component in this portfolio has to beat a written one before it is
allowed to be the headline -- the incident detector lost to a three-line
baseline and that result is published, the meeting classifier beat its keyword
gate and had to show the margin. An agent gets the same treatment.

This is a complete system, not a strawman: it routes, calls the same tools with
the same arguments, and renders an answer from what came back. If the model
cannot beat it, the honest conclusion is that a 0.5B model adds nothing here,
and that is a publishable result rather than one to tune away.

**The comparison's real limit.** The rules and the evaluation tasks were written
by the same person, which is precisely the failure
`autonomous-meeting-intelligence/docs/adr/001` exists to name. A keyword router
scoring well against tasks its author also wrote is weaker evidence than the
same score against tasks someone else wrote. The tasks were fixed before either
system was run, which removes tuning-to-result but not shared-authorship, and
`docs/AGENT.md` says so where the numbers appear.
"""
import re

from tools import REFUSE, invoke, item_text

ACCOUNT = re.compile(r"\bacct_\d+\b", re.IGNORECASE)

# Named because they appear in the services' own data, not because they appear
# in the evaluation tasks.
SERVICES = (
    "checkout", "payments", "search", "auth", "billing", "gateway", "api",
    "notifications", "reporting",
)

# Ordered: the first rule whose pattern appears wins. Ordering matters where a
# task mentions both an account and an incident, and the order encodes which
# question is being asked rather than which words happen to be present.
RULES = (
    ("meeting_extract", (
        "transcript", "meeting notes", "standup", "the call:", "minutes",
    )),
    ("account_score", (
        "propensity", "renewal", "churn", "segment", "how valuable",
        "worth prioritising", "worth prioritizing", "account score",
    )),
    ("active_incidents", (
        "incident", "outage", "currently down", "degraded", "is it broken",
        "ongoing issue",
    )),
    ("customer_decision", (
        "customer wrote", "customer says", "how should we respond",
        "handle this message", "what should we do about this complaint",
    )),
    ("knowledge_search", (
        "err-", "how do i", "how to", "what is", "remediation", "runbook",
        "clause", "policy", "steps", "configure", "reference",
    )),
)


def route(task):
    lowered = task.lower()
    for tool, patterns in RULES:
        if any(pattern in lowered for pattern in patterns):
            return tool
    return REFUSE


def arguments_for(tool, task, defaults=None):
    supplied = dict((defaults or {}).get(tool, {}))
    account = ACCOUNT.search(task)
    service = next((name for name in SERVICES if name in task.lower()), "")
    derived = {
        "knowledge_search": {"query": task},
        "account_score": {"customer_id": account.group(0) if account else ""},
        "active_incidents": {"service": service},
        "customer_decision": {"message": task, "service": service},
        "meeting_extract": {"transcript": task},
    }.get(tool, {})
    for key, value in derived.items():
        if value and not supplied.get(key):
            supplied[key] = value
    return supplied


def render(tool, result):
    """Turn a tool result into an answer, without a model.

    Templates, so the baseline is a system a reviewer could actually ship. It
    cannot paraphrase, and on tasks whose scoring wants a fact stated in prose
    that is a real disadvantage -- one the numbers should show rather than hide.
    """
    raw = result["raw"]
    if tool == "knowledge_search":
        return str(raw.get("answer", "")).strip()
    if tool == "account_score":
        return (f"Account score {raw.get('score')}, segment {raw.get('segment')}.")
    if tool == "active_incidents":
        if "active" in raw:
            state = "an active incident" if raw.get("active") else "no active incident"
            return f"There is {state} on {raw.get('service')}."
        return f"There are {raw.get('active_count', 0)} active incidents."
    if tool == "customer_decision":
        intent = (raw.get("intent") or {}).get("label")
        policy = (raw.get("policy") or {}).get("value")
        action = (raw.get("action") or {}).get("type")
        return f"Intent {intent}; policy {policy}; action {action}."
    if tool == "meeting_extract":
        items = (raw.get("decisions") or []) + (raw.get("action_items") or [])
        if not items:
            return "No decisions or action items found."
        return " ".join(item_text(item) for item in items)
    return ""


def run_task(task, defaults=None, **_):
    """Mirrors `loop.run_task`'s return shape so one scorer grades both."""
    tool = route(task)
    if tool == REFUSE:
        return {
            "task": task, "format": "baseline", "outcome": "refused", "answer": "",
            "tools_called": [], "first_tool": REFUSE, "invalid_calls": 0,
            "steps": [], "steps_used": 1, "seconds": 0.0,
        }

    result, error = invoke(tool, arguments_for(tool, task, defaults))
    if error:
        return {
            "task": task, "format": "baseline", "outcome": "answered",
            "answer": f"The {tool} lookup failed ({error}).",
            "tools_called": [], "first_tool": tool, "invalid_calls": 0,
            "steps": [{"tool": tool, "result": f"error:{error}"}],
            "steps_used": 1, "seconds": 0.0,
        }

    return {
        "task": task, "format": "baseline", "outcome": "answered",
        "answer": render(tool, result), "tools_called": [tool], "first_tool": tool,
        "invalid_calls": 0,
        "steps": [{"tool": tool, "result": "ok", "raw_result": result["raw"]}],
        "steps_used": 1, "seconds": 0.0,
    }
