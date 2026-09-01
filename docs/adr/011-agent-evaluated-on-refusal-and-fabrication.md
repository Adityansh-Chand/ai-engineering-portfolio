# ADR-011 — Score the agent on refusal and fabrication, not just task success

**Status:** Accepted · **Date:** 2026-08

## Context

An agent that calls five services is easy to demonstrate and hard to evaluate.
The demonstrable version is a happy-path transcript: a question goes in, the
right service is called, a plausible sentence comes out. Nothing about that
transcript distinguishes a system that routed correctly from one that guessed
and got lucky, and nothing in it says what happens when the answer is not
available.

A single task-success rate has the same problem in aggregate. Picking the wrong
service and picking the right one and then garbling what it returned are both
failures, they call for opposite fixes, and one number cannot tell them apart.

The two failures that matter operationally are not in the happy path at all: a
question no tool can answer, and a service that is down. Both invite the same
wrong behaviour — answer anyway — and both are cheap to leave untested.

## Decision

**Five metrics over four task categories, against a deterministic baseline.**

Metrics: `first_tool_accuracy` (routing alone), `required_tools_called` (did it
keep going), `task_success` (routing *and* a faithful answer),
`invalid_call_rate` (output that was not a usable tool call), `refusal_accuracy`
and `fabrication_rate`.

Categories: `single_tool`, `chain`, `no_tool` — nothing available can answer it —
and `tool_down`, where the required service is **actually killed** mid-run
before the task is scored.

`agent/baseline.py` routes the same forty tasks by keyword, calls the same
tools, and renders an answer from a template. The model has to beat it.

## Alternatives considered

**One task-success number.** Standard, compact, and the thing every agent demo
reports. Rejected because it is unactionable: this evaluation's most useful
result is the gap between routing accuracy and task success, which a single
number is precisely the average of.

**LLM-as-judge for answer quality.** The current default for grading generated
text, and it would handle paraphrase, which the lexical checks here do not. It
was not available honestly: the only local judge is the 0.5B model under test,
and a model grading its own output is not a measurement. A hosted judge costs
money and reintroduces exactly the vendor-and-version irreproducibility that
[ADR-010](010-local-model-so-llm-metrics-are-reproducible.md) went to trouble to
avoid. The consequence is accepted and stated: a correct paraphrase scores zero,
which understates both systems equally.

**Happy-path tasks only.** Twenty-eight of the forty tasks would still be there
and the headline number would be higher. Rejected because the twelve that would
go are the ones with operational consequence. An agent that answers a question
it cannot answer is worse than one that fails, and that cannot be measured
without asking it questions it cannot answer.

**Simulate the outage with a stub.** Cheaper, deterministic, and already how the
degradation unit tests work in each service. Rejected here because a stubbed
client proves the code path, not the behaviour: the interesting question is what
the *model* writes when a real call really fails, and that needs a real failure.
`scripts/load_test.py` made the same choice for the circuit breaker.

**Reuse the RAG generation evaluation.** It already measures groundedness,
attribution and hallucination on unanswerable questions. It measures the wrong
layer — retrieval answer quality, in the repository that owns it. This one
measures orchestration: which service, in what order, and whether the answer
survives the trip back.

## Consequences

- **Routing and answering are reported separately**, so a system can be shown
  routing well and answering badly. That gap is the first thing to look at and
  the thing a combined score hides.
- **`fabrication_rate` is the metric to read first.** A wrong answer that admits
  the lookup failed is recoverable; a confident invented one is not. It is
  measured against services that were genuinely killed.
- **Word-boundary matching, not substring.** Two checks were unsound when first
  written: the anchor `no` matched inside `know`, passing almost any answer, and
  the forbidden segment `low` matched inside `follow`, scoring a correct "the
  service is down, follow up" as a fabrication. Both errors reward or punish a
  system for the spelling of unrelated words.
- **The baseline and the tasks share an author**, which is the limitation
  [`autonomous-meeting-intelligence` ADR-001](https://github.com/Adityansh-Chand/autonomous-meeting-intelligence/blob/main/docs/adr/001-harden-the-corpus-when-the-score-is-perfect.md)
  exists to name. The tasks were fixed before either system ran, which removes
  tuning-to-result but not shared authorship. Its four routing misses were left
  uncorrected after they were observed, because correcting them would have been
  tuning the opponent against the test.
- **The tool descriptions were revised once after seeing results** — the model
  sent every `ERR-####` question to `active_incidents`. That is iteration on the
  evaluation set, it is the kind that quietly inflates a score, and it is
  disclosed in `docs/AGENT.md` rather than left for a reader to find.

## Revisit when

A model large enough to make chaining routine is affordable here. At that point
`first_tool_accuracy` saturates and stops discriminating, and the interesting
metrics become step efficiency and behaviour under partial failure — both of
which this harness already records and neither of which it currently headlines.
