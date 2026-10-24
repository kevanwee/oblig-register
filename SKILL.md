---
name: obligation-extraction
description: Extract dated or triggerable obligations from an executed contract, or review an amendment's impact on an existing obligations register. Preserve exact quotations, trace dependent dates, and publish evidence-linked updates only after review. Use for contract calendars, obligations registers, changed renewal or notice dates, and amended Business Day definitions.
---

# obligation-extraction

You are reading an executed contract and producing a register of obligations that a
person could be held to. The register is data (`schema/register.schema.json`); the
calendar and the markdown come from it mechanically.

For an **amendment to an existing register**, read
[references/amendment-review.md](references/amendment-review.md) first. That mode preserves
the old register, proposes source-backed changes and requires a decision before publication.
Do not rerun initial extraction and overwrite the existing register.

## Workflow

### 1. Frame

Record `contract`, `parties` (exactly as defined in the contract), `effective_date`,
`expiry` (if fixed), `governing_law`. If the term is defined by reference ("36 months from
the Effective Date"), compute `expiry` and note the computation in a comment.

### 2. Sweep the contract clause by clause

For every clause, ask: *does this require a party to do something, or refrain from
something, by a time or on a trigger?* If yes, create an obligation:

| Field | Rule |
|---|---|
| `id` | kebab-case, meaningful (`insurance-certificate`, not `ob-7`) |
| `obligor` / `obligee` | must match `parties` exactly |
| `category` | payment, delivery, notice, reporting, renewal, termination, insurance, compliance, confidentiality, data, ip, other |
| `description` | one line, imperative, what must happen |
| `clause_ref` | the clause number as printed |
| `verbatim` | **the operative words, quoted exactly.** Not a paraphrase. This is what makes the register checkable. |
| `trigger` | see below |
| `condition` | "only if ..." qualifiers |
| `consequence` | what the contract says happens on failure (cross-reference the clause) |
| `lead_days` | how far ahead a reminder should fire; default 14; longer for anything that needs internal approval |

Do not skip obligations because they are "standard". Confidentiality survival, insurance
maintenance, and audit rights are the ones that get missed.

### 3. Classify the trigger

- `fixed`: an explicit date in the contract.
- `relative`: "within N days after X" / "not less than N days before Y". `anchor` is
  `effective_date`, `expiry`, another obligation's `id`, or `event:<name>`. Use
  `business_days` only where the contract says Business Days (and check the definition).
  Use `months` where the contract says months; never convert months to days.
- `event`: runs from something that has not happened (termination, breach, change of
  control). Name the event; the register's `events:` map dates it later.
- `recurring`: periodic. Set `freq`; `day_of_month` if the contract fixes one; `start` and
  `until` if they differ from effective date and expiry.

If a period is expressed in hours ("within 48 hours") use `event` and put the arithmetic
in `notes`.

### 4. Notice clause

Extract the notice clause into `notice_clause`: `clause_ref`, `verbatim`, `addresses` per
party, and one `methods` entry per permitted method with deemed-receipt parameters:

| Clause wording | Parameters |
|---|---|
| "on delivery" | `offset_days: 0` |
| "three days after posting" | `offset_days: 3` |
| "next Business Day after transmission" | `offset_days: 1, business_days: true` |
| "if sent after 5 pm, the next Business Day" | add `cutoff: "17:00"` |
| "if sent on a non-Business Day, the next Business Day" | `non_working_day_defers: true` |

These map directly onto `sg-deadline`'s `deemed_receipt_date` tool; use it to compute an
actual date when asked.

### 5. Validate and resolve

```bash
obligreg validate register.yaml
obligreg -j SG resolve register.yaml        # every deadline with its trace
obligreg -j SG render register.yaml         # markdown register
obligreg -j SG ics register.yaml -o register.ics
```

Read the resolve output. Anything UNRESOLVED is either an undated event (fine; say so) or
a missing calendar (install `sg-deadline`) or an error in the register (fix it).

### 6. Report

Give the user: the markdown register, the list of undated event-triggered obligations,
and the `.ics` path. Flag any obligation whose `verbatim` you were not certain about.

## Rules

- `verbatim` is a quotation. If you cannot quote it, you have not found the obligation.
- Never compute a deadline in your head. Resolve with the tool and show its trace.
- Never omit an obligation because it looks unimportant. Omit only what is not an
  obligation (recitals, definitions, boilerplate with no performance).
- Where the contract is ambiguous about a trigger, record your reading in `notes` and
  flag it in the report.
