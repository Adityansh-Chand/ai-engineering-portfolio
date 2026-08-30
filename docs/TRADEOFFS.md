# Technical Tradeoff Notes

These projects are designed to be externally reviewable without requiring cloud
accounts, secrets, paid providers, or production datasets. The tradeoffs below
make that boundary explicit.

## Local-First Over Cloud-First

Decision:

- Keep every runnable project usable from a fresh local terminal.
- Include Docker, Compose, Kubernetes manifests, and CI as deployment evidence.
- Avoid live cloud environments and managed infrastructure in the portfolio.

Why:

- Reviewers can reproduce behavior quickly.
- No credentials or billing setup are required.
- The portfolio remains safe to publish publicly.

Production next step:

- Add environment-specific deployment overlays, managed secrets, external
  metrics/logging, and release promotion.

## SQLite Event Stores Over Managed Databases

Decision:

- Use SQLite event persistence for the Python services.
- Use MongoDB in ADAAS when configured, with seeded local data as the fallback.

Why:

- Persistence can be inspected locally.
- Smoke tests can verify event/audit behavior without external services.
- The implementation stays simple enough for code review.

Production next step:

- Move event/audit records to a managed database with migrations, backups,
  retention policies, and operational dashboards.

## Optional API Key Auth Over Full Identity

Decision:

- Protect non-health data endpoints with `X-API-Key` only when `API_KEY` is set.

Why:

- The demos are frictionless by default.
- Reviewers can still verify the auth boundary.
- No identity provider setup is needed.

Production next step:

- Add user identity, scoped authorization, key rotation, audit attribution,
  rate limits, and secret management.

## JSON Metrics Over Full Observability Stack

Decision:

- Expose simple `/metrics` endpoints instead of requiring Prometheus, OpenTelemetry,
  or an external logging platform.

Why:

- Metrics are easy to inspect during a five-minute review.
- Tests can assert that the endpoint exists and returns useful counters.

Production next step:

- Emit structured logs, traces, Prometheus metrics, alert rules, and dashboards.

## Sample Data Over Production Data

Decision:

- Use deterministic sample datasets and sample request/response files.

Why:

- Public repositories should not contain sensitive business, customer, employee,
  broker, finance, or third-party data.
- Evaluation scripts stay repeatable.

Production next step:

- Add data ingestion pipelines, data validation, privacy controls, drift checks,
  and governance processes.

## Focused Documentation Over Large Feature Expansion

Decision:

- Prioritize README accuracy, demo scripts, API examples, tests, diagrams, and
  reviewer guidance.

Why:

- Portfolio reviewers need confidence that the systems run and are thoughtfully
  engineered.
- Adding broad new product features would reduce reviewability and increase
  maintenance risk.

Production next step:

- Convert the strongest demos into deployed case studies with realistic traffic,
  monitoring, release processes, and operational ownership.

## Synthetic Data Over No Data

Decision:

- Fit every model on generated data from a seeded, documented generator.
- Say so prominently in every README, model card, and `/health` response.
- Report results on real public benchmarks where they exist (BEIR, in the RAG repo).

Why:

- Real CRM records, production telemetry and meeting transcripts cannot be
  published, and waiting for them would mean shipping no model at all.
- A fitted model on disclosed synthetic data is an honest artifact. A hand-tuned
  formula presented as a model is not.

Cost, stated plainly:

- These metrics measure how well each model recovers a generating process we
  wrote. They are **not** evidence of real-world performance, and none of these
  models has been validated against real outcomes.

## Designing Evaluations That Can Fail

Decision:

- Split by time where data is temporal, and by template where data is generated
  from phrasings.
- Score the baseline being replaced on the same held-out data.
- Report the ceiling alongside the metric where a ceiling exists.
- Keep results that came out worse than hoped.

Why:

- An evaluation that cannot fail is not evidence. Every one of these repositories
  previously reported a near-perfect score against data written to satisfy the
  code being tested.
- A held-out-template split dropped one classifier from 1.00 to 0.6476. The lower
  number is the real one, and the inflated one is retained and labelled rather
  than deleted, so the lesson survives.

Cost:

- The headline numbers are visibly lower than a portfolio usually advertises.
  That is the intended outcome.
