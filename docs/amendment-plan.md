# Contract amendment impact review: implementation plan

## Outcome

An in-house lawyer supplies the current obligations register, the agreement and an
amendment. The skill reads the documents and proposes the legal interpretation. Code
checks source quotations and stable identifiers, calculates direct/dependent impacts,
and produces a review page. Approval publishes a new register plus a dated calendar
changeset; rejection records the decision without publishing. Earlier files remain intact.

## Boundary

The Python library does not extract or interpret clauses. It validates an explicit,
source-linked amendment plan. Extractors must account for every operative amendment
section, identify ambiguity and distinguish effective date from signature date. A quote
match proves text provenance, not the correctness or completeness of legal interpretation.

The first version accepts saved UTF-8 text with stable offsets; PDF/DOCX material must
be converted and checked by the host before use. No external model, upload service,
notification sending, calendar-account mutation or database is required.

## Deliverables

1. Strict amendment-plan and decision schemas, separate from the register schema.
2. Additive register support for an explicit Business Day rule; preserve the old schema.
3. Evidence validation for both baseline and amendment text, including source hashes,
   exact quotations, declared operative sections and per-section dispositions.
4. Whole-obligation add/replace/remove proposals and tightly scoped register-field changes.
   Propagate expiry, event, effective-date, recurrence and Business Day dependencies.
5. Frozen before/after date traces, recurrence differences, unresolved items and blockers.
   Optional sg-deadline preparation remains in the CLI, with stored calendar evidence.
6. Self-contained local review HTML: original/proposed wording, sources and impacts,
   approval/refusal form and a downloadable decision bound to the package digest.
7. Approval applies the reviewed package to a fresh output directory only. Revalidate
   source/base hashes, proposal, calculations and decision; stage output transactionally.
   Preserve obligation identifiers and existing calendar UID conventions. Removed events
   get explicit cancellation instructions in the changeset; do not claim calendar sync.
8. Studio integration with the pinned engine, local uploads, practice scenarios, guarded
   decisions and downloadable results. The portable page remains an export.
9. Three documented synthetic journeys, regression tests, CLI/SOP/skill updates and CI.

## Acceptance checks

- A renewal date and notice-period amendment changes the notice and dependent dates.
- A Business Day definition change reaches all business-day obligations and descendants.
- Unsupported/multi-jurisdiction definitions and ambiguous effect remain unresolved.
- Missing/altered quotations, documents, source spans, base registers, candidate artifacts
  or stale approval digests prevent publication.
- Every declared operative section has a disposition; unknown legal completeness remains
  visible. Changed sources require a new package and renewed review.
- Approval/rejection never edits the original register. Duplicate output paths are refused.
- New calendar entries keep stable UIDs; modified/removed/recurring entries are accounted for.
- A source change or later calendar refresh cannot silently change a reviewed calculation.
- Original extraction, resolution and ICS tests remain compatible.

## Delivery sequence

Schema and pure calculations -> evidence/impact analysis -> package and decision gate ->
review page and skill -> three full journeys -> packaging/CI -> branch PR and merge.

Validation uses synthetic agreements and approvals and actual deterministic calculations.
It makes no claim of lawyer-authenticated decisions or validated market demand.
