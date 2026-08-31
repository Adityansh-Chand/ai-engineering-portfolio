# ADR-003 — Duplicate the service template rather than share a package

**Status:** Accepted · **Date:** 2026-04

## Context

Five services carry byte-identical copies of `utils/security.py`, `utils/storage.py` and
`utils/logger.py` — API-key checking, a SQLite event store, structured logging. Roughly 120
lines, duplicated five times.

This is the first thing a reviewer notices, and the instinct it triggers is correct in
almost every other context: extract a shared package.

There is a second, sharper reason it looks bad here. These repositories were originally
generated from a template, and the identical `utils/` files are the strongest evidence of
it — md5-identical across four repos, initial commits sixteen seconds apart. Extracting
them would make that evidence disappear.

## Decision

Keep the duplication. Declare the shared service template explicitly in every README, and
say plainly that it is deliberate reuse.

## Alternatives considered

**A shared package on PyPI or a git submodule.** The textbook answer. Rejected on the
property that matters most here: each repository must be **independently clonable and
runnable**. `git clone`, `pip install -r requirements.txt`, run. A shared package makes
that `git clone`, then find and install a second thing from somewhere, and a reviewer
checking one claim now has two repositories to satisfy.

It also buys very little. The duplicated code is 120 lines that have changed twice in the
project's life, and both changes — adding `request_id` to the event store, and enforcing
auth in the integrated compose — were applied across five repositories in one pass without
difficulty. The versioning problem a shared library introduces is strictly larger than the
problem it solves at this size.

**A monorepo.** Solves duplication and independence at once, and is what most teams would
do. Rejected because each repository is a separate portfolio artifact with its own README,
CI, and evaluation, meant to be linked to and reviewed alone. That is a presentation
constraint rather than an engineering one, and it is stated as such.

**Vendoring with a sync script** — one source of truth, copied in by a tool. Genuinely
tempting. Rejected as the worst of both: the files still look duplicated to a reviewer, and
now there is a script that must be run and can silently not have been.

**Extracting it to hide the template origin.** Named because it was considered and is the
wrong reason to do anything. The template origin is a fact about how these repositories
started; the work since is what changes what they are. Removing the evidence would be
managing appearances, which is the failure mode this portfolio was rebuilt to eliminate.

## Consequences

- A reviewer's first impression is copy-paste, and the README has to answer that before it
  can say anything else. Accepted cost.
- A change to shared behaviour is five commits, not one. In practice this has been fine and
  the discipline is enforced by a compose-level validator that fails if the services
  disagree about required configuration.
- Each service genuinely stands alone, which is what makes single-repository review, single
  repository CI, and the standalone-versus-integrated distinction possible at all.
- **The duplication does not extend to domain logic.** That was the actual disease: five
  repositories that looked alike because their domain logic was too thin to push back
  against the template. Their evaluations are now structurally unable to resemble each
  other — chronological splits and rare-event metrics for incidents, held-out templates for
  intent, ranking metrics with human judgments for retrieval. The `utils/` similarity is a
  symptom that was left in place once the disease was treated.

## Revisit when

The shared surface grows past roughly the size of one file, or a change to it needs to
happen faster than five coordinated commits allow. Both are signals that the reuse is no
longer incidental, and incidental reuse is the only kind this ADR is defending.
