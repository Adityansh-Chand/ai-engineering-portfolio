# Project Comparison

This table helps reviewers compare scope, engineering surface, and evidence
across the repositories.

Every metric below is measured on a held-out split and reproducible from the
repository it belongs to. Each row links to the model card carrying the full
result and its limitations.

## What each system actually does

| Project | Model | Data | Split | Headline held-out result |
|---|---|---|---|---|
| `ai-sales-intelligence-engine` | Logistic regression (fitted) | Synthetic, 5,000 accounts | 75/25 stratified | ROC-AUC **0.8614** (Bayes ceiling 0.8898) |
| `ai-incident-detection-platform` | IsolationForest on normal traffic | Synthetic, 40,320 minutes | **Chronological** per service | Precision **0.7895**, F1 0.8077, 17/17 incidents caught |
| `ai-proactive-customer-operations` | 2 × TF-IDF → LogisticRegression | Synthetic, 2,400 messages | **Held-out templates** | Intent macro-F1 **0.6476**, sentiment 0.9121 |
| `autonomous-meeting-intelligence` | TF-IDF → LogisticRegression, 3-class | Synthetic, 3,154 sentences | **Held-out templates** | Macro-F1 **0.5894** vs keyword gate 0.3235 |
| `enterprise-rag-knowledge-system` | BM25 / LSA / dense bi-encoder / RRF | **Real BEIR benchmark** + synthetic demo corpus | Public test qrels | BEIR/NFCorpus nDCG@10 **0.3727** (dense) vs 0.2831 (bm25) |
| `ADAAS` | Keyword intent routing + optional Gemini | Curated 26-entry policy KB | — | Flutter and backend test suites |

## Engineering surface

| Project | Primary Skill Signal | Main Interface | Data Layer | Hardening Baseline | Verification |
|---|---|---|---|---|---|
| `enterprise-rag-knowledge-system` | Retrieval engineering and IR evaluation | FastAPI `/query` | Local corpus, BEIR downloads, SQLite events | Optional API key, request IDs, safe errors, `/metrics`, events | Tests, retrieval bench, smoke test |
| `ai-proactive-customer-operations` | Workflow orchestration with learned front end | FastAPI `/decide` | Generated corpus and SQLite events | Same | Tests, two-level eval, smoke test |
| `ai-incident-detection-platform` | Time-series rare-event detection | FastAPI `/score` | Generated telemetry and SQLite events | Same | Tests, held-out window eval, smoke test |
| `ai-sales-intelligence-engine` | Supervised scoring and attribution | FastAPI `/score` | Generated accounts and SQLite events | Same | Tests, held-out eval, smoke test |
| `autonomous-meeting-intelligence` | Span classification and slot extraction | FastAPI `/analyze` | Generated transcripts and SQLite events | Same | Tests, per-class eval, smoke test |
| `ADAAS` | Full-stack HR assistant integration | Flutter app and Node REST backend | MongoDB when configured, seeded local data otherwise | Optional API key, metrics, health checks, safe API responses | Backend tests, smoke test, Flutter tests/analyze |

## What each repository proves

| Repository | Reviewer takeaway |
|---|---|
| `enterprise-rag-knowledge-system` | Can build and **evaluate** a retrieval system properly: several methods behind one interface, correct IR metrics, real benchmarks, and a per-query-type breakdown showing where each method wins and loses. |
| `ai-proactive-customer-operations` | Can decide what to learn and what to leave as rules. Intent and sentiment are classified; the policy that issues refunds stays deterministic and auditable, and every decision names the rule that fired. |
| `ai-incident-detection-platform` | Can handle time-series correctly — chronological splitting, rare-event metrics rather than accuracy, and a threshold calibrated to an operational precision target. |
| `ai-sales-intelligence-engine` | Can ship a fitted model end to end with attribution that provably reconstructs its own output, and can report a metric alongside the ceiling that makes it interpretable. |
| `autonomous-meeting-intelligence` | Can replace pattern matching with classification and prove the improvement by scoring the thing that was replaced on the same data. |
| `ADAAS` | Can connect backend services to a user-facing application workflow. |

## Evaluation design — the thing these repos have in common

Every one of these evaluations previously reported a near-perfect score and could
not fail. The sales CSV's six rows agreed with a hand-written formula. The ops
sample messages contained the exact keywords the router searched for. The meeting
transcripts said `"Decision:"` because the extractor grepped for `"Decision:"`.
The incident evaluation fitted on rows and then scored those same rows. The RAG
evaluation was two substring-matched queries against a four-sentence corpus.

What changed is mostly evaluation design, and three cases are worth reading:

- **Held-out templates, not rows** (ops, meeting). Splitting by row let the
  classifier memorise phrasings present on both sides and score **1.00**.
  Holding out whole templates dropped that to 0.6476 — and that drop is the
  result. The inflated figure is retained in `metrics.json`, labelled as
  inflated, with a test asserting it stays labelled.
- **Chronological, not random** (incident). Incidents span consecutive minutes,
  so a random split puts the middle of an episode in training and the rest in
  test.
- **Report the ceiling** (sales). ROC-AUC 0.8614 means little alone; against a
  measured Bayes-optimal 0.8898 it means the model captures nearly all available
  signal.

## Results that came out worse than expected, and were kept

A portfolio where every number flatters the author is not evidence of anything.
These are reported as measured:

- **Hybrid retrieval is worse than dense alone** — on the synthetic corpus
  (0.7913 vs 0.8577) *and* on BEIR/NFCorpus (0.3423 vs 0.3727). Equal-weight rank
  fusion can underperform its stronger component when the two are unequal.
  Following it up: the fusion weight was then selected from data on a dev split of
  queries, and **both corpora chose "pure dense, no lexical"**. Weighting fixes the
  underperformance and ties dense exactly, because the optimum is not to fuse. What
  the result actually points at is per-query routing — BM25 scores 1.0 on identifier
  queries and near-zero on paraphrase — which one global weight cannot express.
- **LSA scores below BM25 overall** (0.6544 vs 0.6820). Genuinely semantic,
  genuinely fitted, and on a 108-document corpus not enough to beat a good
  lexical baseline.
- **Reranking changes nDCG@10 by +0.0000.** A measured null result — the fitted
  reranker reorders nothing, because first-stage retrieval at depth 20 already
  reaches 0.8889 and leaves no mistakes to correct. Its learned weights are
  sensible; it simply had no work to do.
- **The incident z-score baseline beats the fitted model on PR-AUC** (0.8597 vs
  0.8523) and catches the same 17/17 incidents. The fitted model's advantage is
  32% fewer false alerts, and that narrower claim is the one made.
- **Owner extraction recalls 0.3484.** Rules that miss full names, titles and
  team references. An earlier corpus scored 1.0 — which proved only that the
  patterns and the generator were written by the same hand.

## Portfolio index

`ai-engineering-portfolio` is the presentation and navigation layer for the six
runnable project repositories. It provides the landing page, reviewer paths,
architecture docs, API flow docs, tradeoff notes, and demo matrix. It is not a
seventh runnable product.

## Shared service template

The five Python services share HTTP hardening (`utils/security.py`), a SQLite
event store (`utils/storage.py`), a metrics surface, and their Docker/Compose/CI
shape. That is deliberate reuse of one service template, stated here so a
reviewer who diffs those files finds what they were told they would find.

The domain logic — retrieval, time-series detection, classification, scoring — is
independent per repository, and so are the evaluation designs, because the
problems genuinely differ.

## Maturity labels

- `synthetic training data`: models are fitted on generated data from a seeded,
  documented generator. Metrics are real measurements on held-out splits; they are
  **not** evidence of real-world performance. The RAG repo additionally reports
  results on public BEIR benchmarks with human relevance judgments.
- `locally tested`: unit tests and evals run without Docker.
- `smoke-tested`: local API smoke tests pass against running services.
- `reproducible artifacts`: committed datasets and models are regenerated and
  re-verified in CI, so the shipped numbers cannot silently drift.
- `Docker config statically validated`: Dockerfile, Compose, and Kubernetes YAML
  are inspected/parsed without starting containers or clusters.
- `Docker image build validated in CI`: GitHub Actions builds service images on
  push and pull requests without pushing to a registry.
- `cloud deployment pending`: no live managed environment is included.
