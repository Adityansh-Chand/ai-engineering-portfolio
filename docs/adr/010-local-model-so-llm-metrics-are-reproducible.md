# ADR-010 — Run the language model locally, so its numbers are reproducible

**Status:** Accepted · **Date:** 2026-08

## Context

Two earlier decisions left a hole between them.

[ADR-007](007-provider-agnostic-llm-seam.md) committed to a
`complete(system, user) -> str` seam with `openai_compatible` and `anthropic`
adapters, so no vendor is hardcoded.
[`enterprise-rag-knowledge-system` ADR-004](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system/blob/main/docs/adr/004-llm-excluded-from-metrics.md)
then excluded the LLM path from every reported metric, because a number that
depends on a vendor, a model version and a sampling temperature is not
reproducible by a reviewer.

Both are right, and together they meant the seam was never exercised. The
portfolio described an LLM integration that no measurement went through — which
reads less like discipline and more like avoidance, and it is the single largest
gap in a portfolio aimed at AI systems work.

There is also a hard constraint: this must cost nothing.

## Decision

**Add a third adapter that runs a small open-weights model on the local CPU, and
build the agent on it.**

`Qwen2.5-0.5B-Instruct`, Apache-2.0, greedy decoding, `torch` and `transformers`
that the repositories already depend on for retrieval embeddings. No API key, no
network at inference time, no bill.

This satisfies the reproducibility objection rather than trading it away: fixed
weights and greedy decoding mean a reviewer on the same machine gets the same
tokens. ADR-004's reasoning is not overturned — it is *met*.

Every number produced this way is reported as what **this** model does, never as
what an LLM does.

## Alternatives considered

**A hosted frontier model.** The obvious way to make the agent good. Rejected on
the stated constraint that this portfolio spends nothing, and on ADR-004's
reproducibility objection, which a hosted model does not answer. The cost of the
road not taken is quantified rather than waved at: `scripts/cost_model.py` puts
the cheapest hosted answer at $1,100 per million against $0.19 for retrieval
compute, and `agent/eval/run.py` prints what each evaluation run would have cost
on each hosted tier next to the $0.00 it actually cost.

**Ollama, llama.cpp or LM Studio.** The normal way to run a local model, and
faster than `transformers` on CPU. Rejected because it adds a runtime to install
and a GGUF quantisation to pin, and `torch` was already a dependency —
`sentence-transformers` has been in the retrieval path since the beginning. The
seam gained an adapter without the portfolio gaining an install step.

**A larger local model.** `Qwen2.5-1.5B` or `3B` would be meaningfully better at
tool selection. The 0.5B model was measured on the development machine at
**3.14 tokens/second** generating from a 219-token prompt; a 1.5B model is
roughly three times the compute per token, which puts a single evaluation run
into the hours on four cores with no GPU. **The larger models were not
benchmarked** — the step down was taken on the measured 0.5B rate and that
projection, not on a measurement of the alternatives, and saying otherwise would
overstate the ladder. `agent/local_llm.py` takes `--model`, so this is a flag
rather than a rewrite.

**Keep excluding LLMs entirely.** Defensible, consistent, and what the portfolio
did until now. Rejected because the gap it leaves is the one that matters most
for the roles this work is aimed at, and because "we measured it and it was bad"
is a far stronger position than "we did not measure it".

## Consequences

- **The seam is now exercised against a second, genuinely different backend.**
  An interface that has only ever had one implementation is a guess; this one
  absorbed an in-process model with no caller changes, which is the first real
  evidence ADR-007 was right.
- **Every agent number is bounded by a 0.5B model** — roughly a thousandth of a
  frontier model's parameters. Results are a floor for what an agent over these
  services can do, never a ceiling, and `docs/AGENT.md` states this wherever the
  numbers appear.
- **3.14 tokens/second sets the whole design.** Tool-selection calls are capped
  at 48 tokens and stopped early, observations are trimmed to a line, the task
  set is forty items rather than four hundred, and repeated identical tool calls
  are detected and broken rather than paid for. A faster model would have hidden
  each of those decisions instead of forcing them.
- **CI still does not run it.** A model download and roughly twenty minutes of
  CPU do not belong in a push-triggered job, so the agent results are measured
  locally and committed, and `scripts/check_agent_wellformed.py` guards in CI
  the part that can rot without a model — tool names, task references and the
  parsers.
- First run downloads about 1 GB of weights to the Hugging Face cache.

## Revisit when

A GPU is available, or the evaluation needs a model whose failures are
interesting rather than obvious. At 0.5B the failure modes are mostly capacity;
the tasks and the harness are the reusable part and take a `--model` flag.
