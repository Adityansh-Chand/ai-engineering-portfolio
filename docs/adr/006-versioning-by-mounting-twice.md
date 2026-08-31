# ADR-006 — Version the API by mounting one router at two prefixes

**Status:** Accepted · **Date:** 2026-05

## Context

Once services call each other, response shapes are cross-repository dependencies (ADR-004).
Contracts alone are not enough — a consumer also needs a way to keep working while a
provider changes, which means the provider needs somewhere to change *to*.

The services already served unversioned paths (`/query`, `/score`, `/events`), and existing
demos, docs and sample requests all used them. Versioning could not break those.

## Decision

Define data endpoints once on an `APIRouter` and mount it twice:

```python
app.include_router(api, prefix=f"/{API_VERSION}")   # /v1/... -- canonical
app.include_router(api, include_in_schema=False)    # /...    -- deprecated alias
```

Contracts target `/v1/...` only. `scripts/check_contracts_wellformed.py` **rejects an
unversioned contract path**, because such a contract would pass today and break the day the
alias is removed — the one failure a contract test exists to prevent.

The alias is excluded from the OpenAPI schema, so the documented surface is versioned even
while the compatible surface is not.

## Alternatives considered

**Duplicate the route definitions under both prefixes.** Rejected immediately: two copies of
every handler drift, and the drift is invisible until a consumer hits the stale one.

**Header-based versioning (`Accept: application/vnd.x.v1+json`).** More RESTful by some
readings. Rejected because it is invisible in a URL, which makes every `curl` in every
README and every captured demo asset ambiguous about which version it exercised. For a
portfolio whose main artifact is reproducible evidence, a version you cannot see in the
command is a bad trade.

**Version the whole app — run `/v1` and `/v2` as separate deployments.** The cleanest answer
when versions genuinely diverge. Rejected as premature: there is one version, and standing
up a second deployment to express that would be architecture for a problem not yet present.

**Break the old paths and update everything at once.** Possible here, since every consumer
is in this workspace. Rejected because it teaches the wrong reflex — the interesting case is
the one where you *cannot* update every consumer at once, and building for the easy case
means the mechanism does not exist when the hard case arrives.

## Consequences

- The alias means the deprecation is real but untested: nothing currently verifies the
  behaviour when it is removed. The well-formedness check is what prevents new dependencies
  on it accumulating in the meantime.
- One router definition, so `/v1/query` and `/query` cannot diverge by construction.
- `include_in_schema=False` keeps the OpenAPI page honest about what is supported, which
  matters because those pages are captured as portfolio assets.
- **This decision caused the one CI failure worth recording.** The versioning tests passed
  locally and failed in CI: FastAPI 0.141.1 / Starlette 1.6.0 in CI against 0.128.4 / 0.52.1
  locally. The endpoints worked identically on both — what changed was `app.routes`
  introspection, which the tests were asserting against. The tests were rewritten to issue
  real requests instead of inspecting the router, and the versions were pinned. Testing the
  framework's internal structure rather than the behaviour is the mistake; the version skew
  only exposed it.

## Revisit when

A second version actually exists. At that point the alias should be removed rather than
carried, and the mechanism for running two versions side by side is already in place — a
second `include_router` with a different prefix and a different router.
