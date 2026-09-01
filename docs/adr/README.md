# Architecture Decision Records

Portfolio-wide decisions: the ones that shaped how five independent services became one
system without stopping being independent.

A record is written when a choice was **contested** — when a competent engineer could
reasonably have gone the other way, and the reason it went this way is not recoverable by
reading the code. Choices with one obvious answer are not recorded. A directory of records
for things nobody would dispute is a directory nobody reads.

Records are immutable once accepted. A decision that changes gets a new record superseding
the old one, and the old one stays, because the reasoning that turned out to be wrong is
usually the more useful half.

| # | Decision | Status |
|---|---|---|
| [001](001-optional-and-degrading-integration.md) | Enrichment may improve a decision, never prevent one | Accepted |
| [002](002-http-fanout-over-message-broker.md) | HTTP fan-out and an outbox, not a message broker | Accepted |
| [003](003-duplicated-template-over-shared-library.md) | Duplicate the service template rather than share a package | Accepted |
| [004](004-consumer-driven-contracts.md) | Consumer-driven contract tests, not a schema registry | Accepted |
| [005](005-request-id-over-opentelemetry.md) | Propagate a request ID; do not adopt OpenTelemetry | Accepted |
| [006](006-versioning-by-mounting-twice.md) | Version the API by mounting one router at two prefixes | Accepted |
| [007](007-provider-agnostic-llm-seam.md) | One narrow LLM seam, no vendor in the call site | Accepted |
| [008](008-model-cost-and-load-locally.md) | Model cost and measure load locally instead of deploying | Accepted |
| [009](009-event-store-is-the-scaling-ceiling.md) | Keep the shared SQLite event store, and record its ceiling | Superseded by 012 |
| [010](010-local-model-so-llm-metrics-are-reproducible.md) | Run the language model locally, so its numbers are reproducible | Accepted |
| [011](011-agent-evaluated-on-refusal-and-fabrication.md) | Score the agent on refusal and fabrication, not just task success | Accepted |
| [012](012-ship-the-event-store-fix.md) | Ship the event store fix | Accepted |

## Decisions recorded elsewhere

Eight further choices — local-first, SQLite event stores, optional API-key auth, JSON
metrics, sample data, documentation focus, synthetic training data, and evaluations
designed to fail — are written up in [`../TRADEOFFS.md`](../TRADEOFFS.md) in a
decision/why/cost form. They are not duplicated here.

Service-specific decisions live in each service's own repository, for example the RAG
service's [`docs/adr/`](https://github.com/Adityansh-Chand/enterprise-rag-knowledge-system/tree/main/docs/adr).
