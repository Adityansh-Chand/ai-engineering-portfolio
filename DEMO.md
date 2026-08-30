# Demo Matrix

This portfolio is best demoed from the individual project repositories. Each
project includes a `DEMO.md`, terminal demo steps, curl commands, and sample
request/response files where applicable.

This repository is an index and demo guide for the six runnable projects, not a
standalone application.

For polished screenshots or terminal recordings, use
[`docs/DEMO_CAPTURE.md`](docs/DEMO_CAPTURE.md).

| Project | Demo Focus | Run Target | Sample Assets |
|---|---|---|---|
| [`enterprise-rag-knowledge-system`](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system) | Retrieval over a mixed-enterprise corpus, with groundedness reported | FastAPI `/query` | `examples/requests/query.json`, `examples/responses/query.json` |
| [`ai-proactive-customer-operations`](https://github.com/Adityansh-Chand/ai-proactive-customer-operations) | Customer message routing, policy, and action trace | FastAPI `/decide` | `examples/requests/decide.json`, `examples/responses/decide.json` |
| [`ai-incident-detection-platform`](https://github.com/Adityansh-Chand/ai-incident-detection-platform) | Telemetry anomaly score from a fitted IsolationForest | FastAPI `/score` | `examples/requests/score.json`, `examples/responses/score.json` |
| [`ai-sales-intelligence-engine`](https://github.com/Adityansh-Chand/ai-sales-intelligence-engine) | Propensity score with exact per-feature attribution | FastAPI `/score` | `examples/requests/score.json`, `examples/responses/score.json` |
| [`autonomous-meeting-intelligence`](https://github.com/Adityansh-Chand/autonomous-meeting-intelligence) | Decisions and action items from a fitted sentence classifier | FastAPI `/analyze` | `examples/requests/analyze.json`, `examples/responses/analyze.json` |
| [`ADAAS`](https://github.com/Adityansh-Chand/ADAAS) | HR assistant backend and Flutter app walkthrough | Node backend + Flutter app | `examples/requests/chat.json`, `examples/responses/chat.json` |

## Recommended Review Order

1. Start with `enterprise-rag-knowledge-system` to show the retrieval bench and the
   per-query-type comparison between BM25, LSA, dense and fusion.
2. Run `ai-proactive-customer-operations` to show a decision trace.
3. Run `ai-incident-detection-platform` and `ai-sales-intelligence-engine` to show scoring services.
4. Run `autonomous-meeting-intelligence` to show structured extraction.
5. Finish with `ADAAS` to show the HR assistant application tying API-backed workflows into a user experience.

## 5-Minute Review Path

For a quick external review, run one API service end to end from the Workspace
folder or from a clone of the target repo:

```bash
cd enterprise-rag-knowledge-system
pip install -r requirements.txt
python -m pytest -q
uvicorn api.server:app --reload --port 8000
```

Then in a second terminal:

```bash
python scripts/smoke_test.py
```

Review `examples/requests/query.json` and `examples/responses/query.json`, then
use the matrix above to choose a second service if time remains.

## Maturity Labels

| Project | Status Labels |
|---|---|
| `enterprise-rag-knowledge-system` | fitted model, synthetic training data, held-out evaluation, reproducible artifacts, locally tested, smoke-tested, Docker config statically validated, image build validated in CI, cloud deployment pending |
| `ai-proactive-customer-operations` | fitted model, synthetic training data, held-out evaluation, reproducible artifacts, locally tested, smoke-tested, Docker config statically validated, image build validated in CI, cloud deployment pending |
| `ai-incident-detection-platform` | fitted model, synthetic training data, held-out evaluation, reproducible artifacts, locally tested, smoke-tested, Docker config statically validated, image build validated in CI, cloud deployment pending |
| `ai-sales-intelligence-engine` | fitted model, synthetic training data, held-out evaluation, reproducible artifacts, locally tested, smoke-tested, Docker config statically validated, image build validated in CI, cloud deployment pending |
| `autonomous-meeting-intelligence` | fitted model, synthetic training data, held-out evaluation, reproducible artifacts, locally tested, smoke-tested, Docker config statically validated, image build validated in CI, cloud deployment pending |
| `ADAAS` | locally tested, smoke-tested, Docker config statically validated, Docker image build validated in CI, cloud deployment pending, needs production data |

## Common Demo Commands

Python services:

```bash
pip install -r requirements.txt
python -m pytest -q
uvicorn api.server:app --reload --port 8000
python scripts/smoke_test.py
```

ADAAS backend:

```bash
cd hr-backend
npm install
npm test
npm start
npm run smoke
```

## What to check if you only have five minutes

Pick any service repo and run:

```bash
python training/train.py --verify
```

It retrains from the committed generator and **fails** if the shipped metrics have
drifted. The dataset equivalent is `python training/generate_*.py --check`. Both
run in CI on every push.

That is the fastest way to confirm the numbers in a README describe the model
actually committed, rather than taking them on trust.

Every model here is trained on **synthetic** data from a seeded generator, and
every README says so at the top. The RAG repo additionally reports results on
public BEIR benchmarks with human relevance judgments.
