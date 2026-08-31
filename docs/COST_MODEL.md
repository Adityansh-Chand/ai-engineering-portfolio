# Cost model

This portfolio runs on one laptop and spends nothing. That is a deliberate choice, and it
is also a gap: an architecture argument that never mentions money is missing the constraint
that usually decides it. This closes the gap without spending anything.

```bash
python scripts/cost_model.py
```

Inputs: [`scripts/pricing.json`](../scripts/pricing.json) · Output:
[`assets/cost-model.json`](assets/cost-model.json)

---

## Method, and what it is allowed to claim

One rule: **measured where measurable, modelled where not, and never mixed up.**

| | source | status |
|---|---|---|
| throughput | `scripts/load_test.py` | **measured**, on the hardware named below |
| latency of optional components | the RAG repo's rerank bench | **measured** |
| unit prices | `scripts/pricing.json` | **dated inputs**, read 2026-08-31, sources cited |
| token counts per call | the prompt `rag/generator.py` actually builds | derived |
| everything else | — | not modelled |

Prices are inputs, not claims. They change; a model that hardcodes them silently goes
stale, so every entry carries the date it was read and the page it came from.

**The load-bearing caveat:** throughput was measured on an Intel Core i7-8650U laptop, and
cost per request is derived from throughput. A cloud vCPU is not this CPU. The *structure*
of this model transfers; the absolute compute figures would need re-measuring on the target
instance. The token costs do not have this problem — they are per-token and hardware-free.

---

## Compute

One task per service at 1 vCPU / 2 GB, priced at each endpoint's **peak** throughput —
not its maximum-concurrency throughput, because both CPU-bound endpoints get *slower in
aggregate* past their peak, and costing at 32 concurrent requests would price the system at
its worst point and call it capacity.

| endpoint | peak req/s | at concurrency | USD / million (x86) | USD / million (ARM) |
|---|---|---|---|---|
| `ops /v1/decide` | 48.5 | 8 | 0.28 | 0.23 |
| `rag /v1/query` | 71.8 | 4 | 0.19 | 0.15 |
| `sales /v1/score` | 77.4 | 4 | 0.18 | 0.14 |

Serving a million retrieval queries costs about **19 cents** of compute. ARM is ~20%
cheaper for identical work, which is the least interesting true thing in this document and
still worth more than most architecture diagrams.

---

## The headline: the LLM path costs 5,759× the retrieval it sits on

| model | standard | 50% prompt-cache hits | Batch API |
|---|---|---|---|
| Claude Haiku 4.5 | $1,100 | $830 | $550 |
| Claude Sonnet 5 | $2,200 | $1,660 | $1,100 |
| Claude Opus 5 | $5,500 | $4,150 | $2,750 |

Per million answers, at 600 input and 100 output tokens per call.

**Retrieval compute: $0.19 per million. The cheapest LLM answer on top of it: $1,100 per
million.** Even with batching and caching, the generation step is three to four orders of
magnitude more expensive than everything underneath it.

This reframes a decision recorded elsewhere on reproducibility grounds. The RAG service
[excludes the LLM path from every reported metric](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system/blob/main/docs/adr/004-llm-excluded-from-metrics.md)
because a number that depends on a vendor and a sampling temperature is not reproducible.
That argument stands on its own — but it is not the only one. The same decision is the
difference between $0.19 and $1,100.

It also changes what the retrieval work is *for*. If generation dominates cost by 5,000×,
then every improvement that lets you send fewer tokens, or skip the call entirely, is worth
more than any improvement to retrieval speed. Which makes two things cost controls that
were not built as cost controls:

- **Abstention.** The check runs *before* the model call, so a question the corpus cannot
  answer is also a call not paid for. At the served operating point roughly 5% of traffic
  is declined — about **$55 per million saved** on Haiku, more on anything larger.
- **Answer length.** Output tokens cost 5× input tokens per token at every model. Halving
  answer length saves more than halving retrieved context.

---

## What the optional components cost

Both are implemented, benchmarked, and off by default. Their latency was measured in the
RAG repository; what this model adds is the price tag next to the quality.

| component | +ms/query | ΔnDCG@10 | +USD / million | × retrieval compute |
|---|---|---|---|---|
| cross-encoder rerank | 1116.4 | **+0.0011** | 15.31 | **80.2×** |
| fitted pairwise rerank | 4.5 | −0.0063 | 0.06 | 0.3× |

The cross-encoder buys +0.0011 nDCG@10 — a difference inside the noise of a 323-query
benchmark — for **80× the compute cost of the retrieval it is correcting**. That decision
was already made on latency grounds (250× the query time). The cost figure says the same
thing in the unit that gets decisions signed off.

The fitted reranker is nearly free and actively slightly worse. Cheap is not a reason.

---

## Sensitivity: which assumptions actually matter

Each assumption moved on its own, from a baseline of **$1,100.19 per million** (retrieval
compute on x86 plus Claude Haiku 4.5 generation). These are computed by
`build_sensitivity()`, not worked out by hand — a first pass at this table by hand had the
context row at −15%, and it is −20.451%.

| change one assumption | USD / million | effect |
|---|---|---|
| ARM instead of x86 | 1,100.15 | **−0.004%** |
| double the retrieval throughput | 1,100.10 | **−0.009%** |
| Opus 5 instead of Haiku 4.5 | 5,500.19 | **+399.9%** |
| Batch API | 550.19 | −49.991% |
| halve the answer length | 850.19 | −22.723% |
| halve the retrieved context | 875.19 | −20.451% |
| **no LLM at all** | **0.19** | **−99.983%** |

Every compute-side lever is a rounding error once generation is switched on. Doubling
retrieval throughput — the thing the load test makes look most urgent — changes the bill by
nine thousandths of one percent. Choosing a different model changes it by 400%.

This is the practical conclusion of the whole model, and it is not what either measurement
would have said alone: **the model choice is worth four orders of magnitude more than the
infrastructure choice.** The load test on its own points squarely at the wrong problem.

The last row is the one to sit with. The system as it actually ships — extractive answers,
no LLM — costs 19 cents per million where the cheapest generative version costs $1,100. The
[measured quality gap](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system#answer-quality--groundedness-is-not-correctness)
between them is real and the extractive path loses it. But that trade is now a number with
two sides rather than an assumption that the generative version is obviously better.

---

## What is not modelled

- **Storage, egress, load balancers, NAT, logging.** Real, and small relative to a
  5,000× term. Omitted rather than guessed.
- **Idle cost.** Everything here is priced per request at peak throughput. A service that
  is provisioned and unused costs its full task rate, and at low traffic that dominates
  entirely — the crossover is around 1 request every 20 seconds, below which you are paying
  for an idle container rather than for work.
- **Embedding generation at index time.** One-off per corpus, not per request.
- **Reserved capacity, Savings Plans, Spot.** All would reduce the compute term, which the
  sensitivity table shows barely matters.
- **Anything actually spent.** No account was opened and no request was billed. This is a
  model built from published prices and local measurements, and it is labelled as one.
