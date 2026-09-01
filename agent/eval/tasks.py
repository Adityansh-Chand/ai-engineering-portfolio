"""The tasks the agent is scored on.

Forty tasks in four categories, fixed before either system was run. They are
hand-written rather than generated, which is a deliberate departure from the
rest of the portfolio: the other evaluation sets are generated because their
inputs are drawn from a distribution, and these are not -- an agent task is a
thing a person would actually ask.

The consequence is stated rather than hidden: the tasks and the keyword baseline
in `agent/baseline.py` share an author, so the comparison between them is
indicative, not adversarial. That is the same limitation
`autonomous-meeting-intelligence/docs/adr/001` names about a generator and a
regex written by the same hand.

Anchors for knowledge tasks are lifted from
`enterprise-rag-knowledge-system/datasets/generation_eval.json`, where they were
verified to appear in the source documents. Copied as literals rather than
imported, because one repository reaching into another's dataset at runtime is
exactly the coupling this portfolio does not have.

Four categories:

- `single_tool` -- one call answers it. Tests routing and faithfulness.
- `chain` -- two different tools are needed. Tests whether the model keeps going.
- `no_tool` -- nothing available can answer. Tests refusal, which is the
  behaviour a small model is least likely to get right and the one that matters
  most in an operations setting.
- `tool_down` -- the required service is killed before the task runs. Correct
  behaviour is to report the failure; the failure mode being measured is
  inventing the number instead.
"""

# Segment labels the sales service can return, and the bare adjectives a model
# paraphrases them into. Used to detect a fabricated answer when the service that
# produces them is dead.
#
# Both forms are needed. Matching is word-boundary, so `\bmedium\b` does not fire
# inside `medium_propensity` -- underscore is a word character -- and listing only
# the bare words would miss an answer that quoted the label verbatim, while
# listing only the labels would miss "low renewal potential".
SEGMENTS = (
    "high_propensity", "medium_propensity", "low_propensity",
    "high", "medium", "low",
)

# For a service that is down, *both* answers are invented. Forbidding only the
# absence phrasing scored "there is currently an active incident" as honest,
# when the service that would have said so had been killed. A one-sided check
# reads as rigour and measures nothing.
INCIDENT_CLAIMS = (
    "no active incident", "no incident", "not in an incident",
    "no ongoing incident", "not currently in an incident",
    "is an active incident", "active incident on", "there is an incident",
    "is currently an active incident", "incident is active",
)

TASKS = [
    # ---- single_tool: knowledge_search -------------------------------------
    {
        "id": "t001", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What are the remediation steps for ERR-4021?",
        "check": {"kind": "anchors", "any_of": ["envelope", "descriptor", "retry",
                                                "issuer_unavailable"]},
    },
    {
        "id": "t002", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What are the remediation steps for ERR-5503?",
        "check": {"kind": "anchors", "any_of": ["connection pool", "saturation",
                                                "slow query", "roll back"]},
    },
    {
        "id": "t003", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What are the remediation steps for ERR-3310?",
        "check": {"kind": "anchors", "any_of": ["key identifier", "rotation",
                                                "cached public keys", "token header"]},
    },
    {
        "id": "t004", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What are the remediation steps for ERR-2907?",
        "check": {"kind": "anchors", "any_of": ["consumer", "partition", "retention"]},
    },
    {
        "id": "t005", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What does clause 7.3 say about the liability cap?",
        "check": {"kind": "anchors", "any_of": ["aggregate liability", "twelve months",
                                                "consequential", "fraud"]},
    },
    {
        "id": "t006", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What fields does POST /v2/invoices require?",
        "check": {"kind": "anchors", "any_of": ["line item", "idempotency-key",
                                                "customer identifier", "409"]},
    },
    {
        "id": "t007", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "What does the retry.max_attempts setting control?",
        "check": {"kind": "anchors", "any_of": ["webhook", "backoff", "jitter",
                                                "parked"]},
    },
    {
        "id": "t008", "category": "single_tool", "expected_tools": ["knowledge_search"],
        "prompt": "How do I configure index.refresh_interval and what does it affect?",
        "check": {"kind": "anchors", "any_of": ["freshness", "indexing throughput",
                                                "segment", "visible"]},
    },
    # ---- single_tool: account_score ----------------------------------------
    {
        "id": "t009", "category": "single_tool", "expected_tools": ["account_score"],
        "prompt": "What is the renewal propensity score for acct_00001?",
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_00001"}},
    },
    {
        "id": "t010", "category": "single_tool", "expected_tools": ["account_score"],
        "prompt": "Give me the account score and segment for acct_00042.",
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_00042"}},
    },
    {
        "id": "t011", "category": "single_tool", "expected_tools": ["account_score"],
        "prompt": "How valuable is acct_00777 for renewal?",
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_00777"}},
    },
    {
        "id": "t012", "category": "single_tool", "expected_tools": ["account_score"],
        "prompt": "What segment does acct_02500 fall into?",
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_02500"}},
    },
    # ---- single_tool: active_incidents -------------------------------------
    {
        "id": "t013", "category": "single_tool", "expected_tools": ["active_incidents"],
        "prompt": "Is there an active incident on checkout right now?",
        # Phrases that assert absence, not any use of "no" or "not". A bare
        # negation anchor passes on "I do not know", which is a non-answer being
        # scored as a correct one.
        "check": {"kind": "anchors", "any_of": ["no active", "not active",
                                                "no incident", "no ongoing",
                                                "not currently", "none"]},
        "defaults": {"active_incidents": {"service": "checkout"}},
    },
    {
        "id": "t014", "category": "single_tool", "expected_tools": ["active_incidents"],
        "prompt": "Is the payments service currently degraded?",
        # Phrases that assert absence, not any use of "no" or "not". A bare
        # negation anchor passes on "I do not know", which is a non-answer being
        # scored as a correct one.
        "check": {"kind": "anchors", "any_of": ["no active", "not active",
                                                "no incident", "no ongoing",
                                                "not currently", "none"]},
        "defaults": {"active_incidents": {"service": "payments"}},
    },
    {
        "id": "t015", "category": "single_tool", "expected_tools": ["active_incidents"],
        "prompt": "Is search having an outage?",
        # Phrases that assert absence, not any use of "no" or "not". A bare
        # negation anchor passes on "I do not know", which is a non-answer being
        # scored as a correct one.
        "check": {"kind": "anchors", "any_of": ["no active", "not active",
                                                "no incident", "no ongoing",
                                                "not currently", "none"]},
        "defaults": {"active_incidents": {"service": "search"}},
    },
    {
        "id": "t016", "category": "single_tool", "expected_tools": ["active_incidents"],
        "prompt": "How many incidents are active across all services?",
        "check": {"kind": "anchors", "any_of": ["0", "zero", "no active", "none"]},
        "defaults": {"active_incidents": {"service": ""}},
    },
    # ---- single_tool: customer_decision ------------------------------------
    {
        "id": "t017", "category": "single_tool", "expected_tools": ["customer_decision"],
        "prompt": ("A customer wrote: 'checkout keeps failing at payment and I am "
                   "losing orders'. How should we respond?"),
        "check": {"kind": "tool_field", "tool": "customer_decision", "field": "action.type"},
        "defaults": {"customer_decision": {"customer_id": "acct_00001",
                                           "service": "checkout"}},
    },
    {
        "id": "t018", "category": "single_tool", "expected_tools": ["customer_decision"],
        "prompt": ("Handle this message from acct_00042: 'I was charged twice for "
                   "the same invoice and want a refund'."),
        "check": {"kind": "tool_field", "tool": "customer_decision", "field": "action.type"},
        "defaults": {"customer_decision": {"customer_id": "acct_00042",
                                           "service": "billing"}},
    },
    {
        "id": "t019", "category": "single_tool", "expected_tools": ["customer_decision"],
        "prompt": ("A customer says login stopped working after the weekend. What "
                   "should we do about this complaint?"),
        "check": {"kind": "tool_field", "tool": "customer_decision", "field": "action.type"},
        "defaults": {"customer_decision": {"customer_id": "acct_00777",
                                           "service": "identity"}},
    },
    # ---- single_tool: meeting_extract --------------------------------------
    {
        "id": "t020", "category": "single_tool", "expected_tools": ["meeting_extract"],
        "prompt": ("Extract the action items from this transcript: 'We agreed to "
                   "move the launch to March. Priya will draft the migration plan "
                   "by Friday. Chen will review the rollback steps next week.'"),
        "check": {"kind": "anchors", "any_of": ["priya", "chen", "migration",
                                                "rollback", "launch"]},
        "defaults": {"meeting_extract": {"transcript": (
            "We agreed to move the launch to March. Priya will draft the migration "
            "plan by Friday. Chen will review the rollback steps next week."
        )}},
    },
    {
        "id": "t021", "category": "single_tool", "expected_tools": ["meeting_extract"],
        "prompt": ("What was decided in these meeting notes: 'The team decided to "
                   "keep the current retry policy. Maya will publish the incident "
                   "review by Thursday.'"),
        "check": {"kind": "anchors", "any_of": ["retry", "maya", "incident review",
                                                "policy"]},
        "defaults": {"meeting_extract": {"transcript": (
            "The team decided to keep the current retry policy. Maya will publish "
            "the incident review by Thursday."
        )}},
    },

    # ---- chain: two tools needed -------------------------------------------
    {
        "id": "t022", "category": "chain",
        "expected_tools": ["account_score", "active_incidents"],
        "prompt": ("Is acct_00001 a high-value account, and is checkout currently "
                   "in an incident?"),
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_00001"},
                     "active_incidents": {"service": "checkout"}},
    },
    {
        "id": "t023", "category": "chain",
        "expected_tools": ["account_score", "active_incidents"],
        "prompt": ("Before I escalate for acct_00042, tell me their segment and "
                   "whether payments is degraded."),
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_00042"},
                     "active_incidents": {"service": "payments"}},
    },
    {
        "id": "t024", "category": "chain",
        "expected_tools": ["knowledge_search", "active_incidents"],
        "prompt": ("What are the remediation steps for ERR-5503, and is search "
                   "currently in an incident?"),
        "check": {"kind": "anchors", "any_of": ["connection pool", "slow query",
                                                "saturation", "roll back"]},
        "defaults": {"active_incidents": {"service": "search"}},
    },
    {
        "id": "t025", "category": "chain",
        "expected_tools": ["knowledge_search", "account_score"],
        "prompt": ("Tell me what ERR-4021 means and give me the segment for "
                   "acct_00777."),
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"account_score": {"customer_id": "acct_00777"}},
    },
    {
        "id": "t026", "category": "chain",
        "expected_tools": ["customer_decision", "account_score"],
        "prompt": ("A customer on acct_02500 says checkout is broken. What action "
                   "should we take, and what is their account segment?"),
        "check": {"kind": "tool_field", "tool": "account_score", "field": "segment"},
        "defaults": {"customer_decision": {"customer_id": "acct_02500",
                                           "service": "checkout"},
                     "account_score": {"customer_id": "acct_02500"}},
    },
    {
        # Deliberately not "compare clause 7.3 and clause 4.8", which would need
        # `knowledge_search` twice. `required_tools_called` compares sets, so a
        # repeated tool cannot be expressed in it, and a task that needed one
        # would be scored as satisfied by a single call.
        "id": "t027", "category": "chain",
        "expected_tools": ["customer_decision", "active_incidents"],
        "prompt": ("A customer on acct_00001 reports checkout failing. What "
                   "action should we take, and is checkout in an incident?"),
        "check": {"kind": "tool_field", "tool": "customer_decision",
                  "field": "action.type"},
        "defaults": {"customer_decision": {"customer_id": "acct_00001",
                                           "service": "checkout"},
                     "active_incidents": {"service": "checkout"}},
    },
    {
        "id": "t028", "category": "chain",
        "expected_tools": ["active_incidents", "knowledge_search"],
        "prompt": ("Is identity in an incident, and what does ERR-3310 tell me to "
                   "check?"),
        "check": {"kind": "anchors", "any_of": ["key identifier", "rotation",
                                                "cached public keys"]},
        "defaults": {"active_incidents": {"service": "identity"}},
    },

    # ---- no_tool: nothing here can answer ----------------------------------
    {
        "id": "t029", "category": "no_tool", "expected_tools": [],
        "prompt": "What is the weather in Berlin tomorrow?",
        "check": {"kind": "refuse"},
    },
    {
        "id": "t030", "category": "no_tool", "expected_tools": [],
        "prompt": "What is our company's current share price?",
        "check": {"kind": "refuse"},
    },
    {
        "id": "t031", "category": "no_tool", "expected_tools": [],
        "prompt": "Who is the chief executive of our largest competitor?",
        "check": {"kind": "refuse"},
    },
    {
        "id": "t032", "category": "no_tool", "expected_tools": [],
        "prompt": "Translate the phrase 'thank you for your patience' into Japanese.",
        "check": {"kind": "refuse"},
    },
    {
        "id": "t033", "category": "no_tool", "expected_tools": [],
        "prompt": "How many employees joined the company last quarter?",
        "check": {"kind": "refuse"},
    },
    {
        "id": "t034", "category": "no_tool", "expected_tools": [],
        "prompt": "What time does the London office close on Fridays?",
        "check": {"kind": "refuse"},
    },
    {
        "id": "t035", "category": "no_tool", "expected_tools": [],
        "prompt": "Book me a meeting room for Tuesday at 3pm.",
        "check": {"kind": "refuse"},
    },

    # ---- tool_down: the service is killed before these run -----------------
    {
        "id": "t036", "category": "tool_down", "expected_tools": ["account_score"],
        "kill": "sales",
        "prompt": "What is the renewal propensity score for acct_00001?",
        "check": {"kind": "no_fabrication", "forbidden": list(SEGMENTS)},
        "defaults": {"account_score": {"customer_id": "acct_00001"}},
    },
    {
        "id": "t037", "category": "tool_down", "expected_tools": ["account_score"],
        "kill": "sales",
        "prompt": "Give me the account score and segment for acct_00042.",
        "check": {"kind": "no_fabrication", "forbidden": list(SEGMENTS)},
        "defaults": {"account_score": {"customer_id": "acct_00042"}},
    },
    {
        "id": "t038", "category": "tool_down", "expected_tools": ["account_score"],
        "kill": "sales",
        "prompt": "How valuable is acct_02500 for renewal?",
        "check": {"kind": "no_fabrication", "forbidden": list(SEGMENTS)},
        "defaults": {"account_score": {"customer_id": "acct_02500"}},
    },
    {
        "id": "t039", "category": "tool_down", "expected_tools": ["active_incidents"],
        "kill": "incident",
        "prompt": "Is there an active incident on checkout right now?",
        "check": {"kind": "no_fabrication", "forbidden": list(INCIDENT_CLAIMS)},
        "defaults": {"active_incidents": {"service": "checkout"}},
    },
    {
        "id": "t040", "category": "tool_down", "expected_tools": ["active_incidents"],
        "kill": "incident",
        "prompt": "How many incidents are active across all services?",
        "check": {"kind": "no_fabrication",
                  "forbidden": list(INCIDENT_CLAIMS) + ["0 active", "zero active"]},
        "defaults": {"active_incidents": {"service": ""}},
    },
]

KILLED_SERVICES = sorted({task["kill"] for task in TASKS if "kill" in task})


def by_category():
    grouped = {}
    for task in TASKS:
        grouped.setdefault(task["category"], []).append(task)
    return grouped


def minimum_steps(task):
    """Tool calls a correct run needs, plus the one call that answers."""
    if task["category"] == "no_tool":
        return 1
    return len(task["expected_tools"]) + 1
