# ADR-007 — One narrow LLM seam, no vendor in the call site

**Status:** Accepted · **Date:** 2026-04

## Context

Three services have a natural place for a language model: intent and sentiment
classification in customer operations, decision and action-item extraction from meeting
transcripts, and answer generation in retrieval.

There was already a cautionary example in the codebase. The RAG service had
`EMBEDDING_PROVIDER = "local"` — a setting shaped exactly like a plug point, which raised on
every value except one. Configuration that looks pluggable and is not is worse than no
configuration at all, because it makes a claim the code cannot honour.

## Decision

One seam, `llm/client.py`, roughly `complete(system, user) -> str`. Callers never learn which
provider is configured.

```
LLM_PROVIDER   openai_compatible | anthropic | none      (default: none)
LLM_API_KEY    operator's key
LLM_MODEL      operator-supplied model identifier
LLM_BASE_URL   endpoint (optional; enables self-hosted and gateways)
```

`openai_compatible` is the primary adapter, because that request shape is spoken natively or
through a compatibility endpoint by most providers and local runtimes — Ollama, vLLM, LM
Studio, OpenRouter. `LLM_BASE_URL` is what makes local and self-hosted work. `anthropic` is a
second adapter on the native Messages API. `none` is the default: the local classifier runs,
no network, nothing changes in CI.

**An unrecognised `LLM_PROVIDER` fails with an error naming the supported values** — the
specific thing the `EMBEDDING_PROVIDER` stub did not do.

## Alternatives considered

**Pick one vendor and call its SDK directly.** Simplest, and what most projects do. Rejected
because it puts a vendor in every call site, and because the operator running this is not
the author — a reviewer with an OpenRouter key, or Ollama on their laptop, should not need
to edit code.

**Use LangChain or a similar abstraction layer.** It solves this problem and many others.
Rejected on proportion: the seam needed is one function returning a string, and a framework
dependency to obtain it would be the largest dependency in these repositories, added for the
smallest interface in them.

**No LLM support at all.** Defensible, given that [no reported metric may come from the LLM
path](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system/blob/main/docs/adr/004-llm-excluded-from-metrics.md).
Rejected because the seam is honest as built, costs nothing when unset, and the *capability*
is worth demonstrating even when the results are not reported.

**Two adapters when one would do.** `openai_compatible` alone covers most of the world
through compatibility endpoints. The second adapter exists because an interface with one
implementation has never had its abstraction tested — the same argument as ADR-001 in the
RAG repository. Writing the Anthropic adapter is what proved `complete(system, user)` was
actually provider-shaped rather than OpenAI-shaped.

## Consequences

- Every README states which providers were actually exercised and which are untested. That
  distinction is the difference between this and the stub it replaced.
- All reported metrics come from the local path, so CI never needs a key and results never
  depend on a vendor, a model version, or a sampling temperature.
- The cost of the path it enables is now quantified: [the LLM path costs roughly 5,759× the
  retrieval compute it sits on](../COST_MODEL.md). The seam being off by default is not only
  a reproducibility decision.
- Two adapters is two things to keep working against APIs that change, with no automated
  test that they still do. This is the weakest point: the adapters are exercised manually,
  not in CI, because CI has no key.

## Revisit when

A locally-runnable open model can be pinned by weights hash and run in CI. That removes the
key, the vendor and the version drift at once, and turns the untested-adapter problem into an
ordinary test.
