# ADR-004 — Consumer-driven contract tests, not a schema registry

**Status:** Accepted · **Date:** 2026-05

## Context

Once ops reads `score` and `segment` from the sales service, and `active` from the incident
service, and `response.answer` from retrieval, those field names are load-bearing across
repository boundaries. Nothing in five separate repositories with five separate CI runs
notices when a provider renames one.

The failure mode is specific and quiet: the provider's tests pass, the consumer's tests
pass (its integration client is stubbed), and the break appears only when the two run
together — which, given the degradation design in ADR-001, means it appears as an
enrichment silently falling back rather than as an error. **The safety property that makes
integration safe is the same property that hides integration breakage.**

## Decision

A single `contracts/contracts.json` in the portfolio repository, recording what each
*consumer* actually reads from each *provider* — the consumer's code location, the request
it makes, and the fields it depends on. `scripts/verify_contracts.py` stands the services
up and checks each contract against a live response.

Fields not listed are explicitly **not** depended on, and providers may change them freely.

## Alternatives considered

**A schema registry, or OpenAPI schemas as the contract.** The provider publishes its full
schema and consumers validate against it. Rejected because it records what a provider
*offers*, not what a consumer *needs*, and those differ enormously — the RAG query response
has a dozen fields and ops reads four. A provider changing any of the other eight would
fail a schema check for no reason, and the resulting noise is how schema checks come to be
ignored. Adding `answer_sources` to the RAG response is exactly this case: additive, and
correctly a non-event.

**Pact or a similar contract-testing framework.** The right tool at team scale, with broker
infrastructure to match. Rejected as more machinery than five services and eight contracts
justify; the JSON file plus a verifier script is about eighty lines and does the same job
at this size.

**End-to-end tests instead.** The stack already has an end-to-end demo. Rejected as a
substitute: an end-to-end test tells you *something* broke, and a contract check tells you
which consumer depended on which field. When the failure mode is a silent fallback, the
difference between those two is most of the diagnosis.

**Nothing — rely on the degradation path.** Genuinely defensible, since a broken contract
degrades rather than crashes. Rejected because a system that quietly stops enriching and
never says so is indistinguishable from one that was never configured, and the whole value
of the enrichment disappears without anybody noticing.

## Consequences

- Contracts are verified against **live services**, not fixtures, so a passing check means
  the field was really returned rather than really written down.
- The file must be updated by hand when a consumer starts reading a new field, and nothing
  forces that. This is the weakest point of the design: an undeclared dependency is
  invisible to the checker. Mitigated only by each contract naming the consumer function
  that reads it, so review has somewhere to look.
- Providers get an explicit licence to change unlisted fields, which is the point — it
  makes the contract a small, deliberate surface instead of an accidental one.
- The contracts file also documents the integration topology better than a diagram does,
  because it cannot drift from what the code does without the verifier failing.

## Revisit when

The number of contracts outgrows one file, or a consumer outside this portfolio appears.
Either makes a real contract broker worth its setup cost, and this file is already in the
shape a broker would ingest.
