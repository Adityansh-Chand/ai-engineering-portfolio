# Project Comparison

This table helps reviewers compare scope, engineering surface, and evidence
across the repositories.

| Project | Primary Skill Signal | Main Interface | Data Layer | Hardening Baseline | Verification |
|---|---|---|---|---|---|
| `enterprise-rag-knowledge-system` | Retrieval engineering and grounded answers | FastAPI `/query` | Local corpus and SQLite event store | Optional API key, request IDs, safe errors, `/metrics`, events | Tests, retrieval eval, smoke test |
| `ai-proactive-customer-operations` | Workflow orchestration and decision traces | FastAPI `/decide` | Domain sample data and SQLite event store | Optional API key, request IDs, safe errors, `/metrics`, events | Tests, policy/action eval, smoke test |
| `ai-incident-detection-platform` | Operational anomaly scoring | FastAPI `/score` | Telemetry sample data and SQLite event store | Optional API key, request IDs, safe errors, `/metrics`, events | Tests, scoring eval, smoke test |
| `ai-sales-intelligence-engine` | Predictive scoring and explanation | FastAPI `/score` | Account sample data and SQLite event store | Optional API key, request IDs, safe errors, `/metrics`, events | Tests, scoring eval, smoke test |
| `autonomous-meeting-intelligence` | Transcript structuring | FastAPI `/analyze` | Transcript sample data and SQLite event store | Optional API key, request IDs, safe errors, `/metrics`, events | Tests, structure eval, smoke test |
| `ADAAS` | Full-stack HR assistant integration | Flutter app and Node REST backend | MongoDB when configured, seeded local data otherwise | Optional API key, metrics, health checks, safe API responses | Backend tests, smoke test, Flutter tests/analyze |
| `ai-systems-portfolio` | Portfolio packaging and review path | Markdown docs and demo matrix | JSON demo matrix | Consistent reviewer guidance | Link and JSON validation |

## What Each Repository Proves

| Repository | Reviewer Takeaway |
|---|---|
| `enterprise-rag-knowledge-system` | Can build a source-backed retrieval service with measurable behavior. |
| `ai-proactive-customer-operations` | Can model multi-step business decisions with inspectable traces. |
| `ai-incident-detection-platform` | Can turn operational telemetry into explainable anomaly signals. |
| `ai-sales-intelligence-engine` | Can expose scoring models through a clean API contract. |
| `autonomous-meeting-intelligence` | Can convert unstructured meeting text into structured records. |
| `ADAAS` | Can connect backend services to a user-facing application workflow. |
| `ai-systems-portfolio` | Can package multiple systems into a coherent external review experience. |

## Maturity Labels

All runnable repositories currently share these labels:

- `runnable demo`: local setup, tests, sample data, and smoke tests are present.
- `deployable baseline`: Docker, Compose, Kubernetes manifests, and CI exist.
- `needs cloud deployment`: no live managed environment is included.
- `needs production data`: datasets are intentionally local demo/sample data.
