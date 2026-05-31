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
