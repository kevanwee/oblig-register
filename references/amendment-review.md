# Contract amendment impact review

Use this mode when an existing obligation register must be updated after a contract
amendment. The lawyer supplies the current register, its complete operative agreement
pack, the amendment, the review date and evidence of execution/effectiveness.

## Prepare a proposal

1. Preserve all originals. Confirm whether earlier amendments already form part of the
   baseline. Check every existing obligation's `verbatim` against that agreement pack.
2. Read the whole amendment. Account for each paragraph, including schedules, definitions,
   effect clauses and execution conditions. Classify it as a proposed change, unaffected
   with reasons, or an unresolved question. Code checks character coverage, not whether
   that classification is legally correct.
3. Create `proposal.json` against `schema/amendment.schema.json`. See the three complete
   examples in `examples/amendments/`. Sources are UTF-8 text saved from inspected
   documents; record the original document/page relationship in each `locator`. Offsets
   are zero-based Unicode character offsets after UTF-8 BOM removal; end is exclusive.
   Hash the **raw saved bytes**, preserving line endings. An image or PDF needs inspected
   text extraction first; the engine never verifies that extraction against the PDF.
4. Each change names its target, exact normalized `before` value, explicit `after`,
   rationale and amendment evidence. Normalize the current register using
   `load_register(...).model_dump(mode="json")`. Preserve contract and obligation IDs.
   Replace a whole obligation when its trigger changes. Its new `verbatim` must quote
   actual operative amendment wording; never manufacture a consolidated quotation.
5. Shared fields can change expiry, effective date, events, governing law, notice clause
   or `business_day_rule`. The latter is an explicit reading, with its own quotation:
   `jurisdiction` requires a matching official calendar; `explicit` uses only the stated
   weekends/dates; `unresolved` keeps uncertainty visible. Never use `explicit` to imply
   unknown public holidays are working days. Multi-location bank-opening tests, hours,
   deemed service cut-offs and bespoke conventions need separate legal treatment.
6. Record questions whenever meaning, execution, effectiveness or coverage is uncertain.
   Do not mark execution confirmed just because an execution block exists. For synthetic
   practice set `synthetic: true` and label every decision accordingly.

## Review and publish

Build with `obligreg amend build --base register.yaml --plan proposal.json --out review-v2`.
For Singapore jurisdiction calendars use `obligreg -j SG amend build ...`; install the
current `sg-deadline` engine first. It prepares official calendars at the CLI boundary,
then freezes them into the package. `--offline` forbids retrieval, `--calendar-cache`
selects the cache. Missing coverage prevents publication; do not substitute weekdays.

Inspect before/after values, evidence, direct/shared-field/dependent impacts, traces,
recurrences and pending events. Notice-clause changes flag notice/renewal obligations
for review; they do **not** calculate deemed-service cut-offs automatically. Conditions
and legal adequacy remain the reviewer's judgement. Unchanged undated obligations remain
undated and are omitted from ICS, not silently treated as completed.

In the local HTML report accept or defer/reject every change, acknowledge every affected
obligation, and record the responsible lawyer's name, authority and review basis. Download
the decision. Studio can use the same backend to collect this decision in its workspace.
An actor name is an attestation, not identity verification. Do not simulate it on a real
matter. Approval is all-or-nothing; partial acceptance requires a revised proposal.

Run `obligreg amend apply --base register.yaml --plan proposal.json --review review-v2
--decision amendment-decision.json --out approved-v2` (one command). Input hashes, frozen
sources, recomputed impacts, review presentation and decision fingerprint are checked.
Changed inputs require a new review. Approval blockers cannot be overridden by the UI.

Approval writes a new YAML register, ICS, resolution, decision and receipt. Rejection
writes only a decision and receipt. Existing output directories are never overwritten.
Apply calendar updates and cancellations separately and verify the external result;
an ICS export is not evidence that a calendar changed or a notice was served.
