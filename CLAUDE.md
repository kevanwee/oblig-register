# CLAUDE.md — oblig-register

Engineering conventions for this repository. They bind AI assistants and humans equally.

## What this is

A schema for contract obligations, a resolver that turns triggers into dates with a
trace, an `.ics` writer, and a skill that does the extraction. The library never reads a
contract; it reads a register.

## Non-negotiables

1. **`verbatim` is mandatory and is a quotation.** The schema enforces a minimum length;
   the skill enforces that it is the operative words. Do not relax either. A register
   without quotations is a list of guesses.
2. **Never approximate business days as calendar days.** Without a working-day calendar,
   a business-day period is UNRESOLVED with a reason. This is a feature.
3. **Never approximate months as days.** Months use calendar arithmetic (`relativedelta`).
4. **Event-triggered obligations stay unresolved until dated.** Do not invent a placeholder
   date. `events:` in the register is the only way to date them.
5. **Every resolved date carries a trace.** Add trace lines freely; never remove them.
6. **ICS UIDs are stable** (`<contract-slug>-<obligation-id>@oblig-register`). Changing the
   scheme orphans everyone's calendar entries.
7. **Schema changes are versioned.** `schema/register.schema.json` is generated and a test
   fails on drift. Renaming or removing a field is a major version.

## Layout

```
SKILL.md                     extraction skill (repo root is the skill directory)
schema/register.schema.json  generated: `obligreg schema > schema/register.schema.json`
src/obligreg/
  models.py                  Register / Obligation / Trigger / NoticeClause + loader
  resolve.py                 trigger -> date with trace; dependency-ordered; calendar Protocol
  ics.py                     RFC 5545 writer (hand-rolled; folding, escaping, RRULE, VALARM)
  render.py                  markdown register + upcoming()
  cli.py                     argparse; optional sg-deadline calendar wiring lives here
examples/                    fictional register exercising every trigger kind
tests/
```

## Testing discipline

- `examples/sample-register.yaml` exercises every trigger kind and the notice clause.
  Tests assert literal dates computed by hand (with the derivation in a comment). Keep the
  sample small enough that a reviewer can re-derive every date.
- Business-day tests use a weekday-only stub calendar so the suite does not depend on
  sg-deadline; one `importorskip` test covers the real integration.
- ICS output is asserted line-by-line for the parts that matter (RRULE, VALARM, UID, line
  folding). If you add an ICS property, assert it.
- `python -m pytest` and `ruff check src tests` before every commit.

## Style

- Python 3.11+, type hints, pydantic v2 for the schema, dataclasses for results.
- Line length 100.
- The calendar dependency is a `Protocol` (`add_working_days`). Do not import sg-deadline
  in the library; only `cli.py` wires it, optionally.
- Register YAML: quote clause refs (`"3.1"`, otherwise YAML reads a float), use `>` for
  long verbatim strings, one blank line between obligations.

## Legal-content conventions

- `obligor` and `obligee` use the parties' names exactly as in `parties`.
- `description` is imperative and one line. Detail goes in `verbatim` and `notes`.
- `consequence` cross-references the clause that imposes it.
- Where the extractor had to interpret an ambiguous trigger, the interpretation is in
  `notes`, not silently baked into the trigger.

## Commit hygiene

- Imperative subject, scoped: `resolve: support event anchors in chains`.
- Schema changes and example changes are separate commits.
- No AI attribution lines or co-author trailers.

## What not to build here

- Contract text parsing or clause extraction in Python. The skill does that with the
  document in front of it.
- Email/Slack reminders. Export ICS; calendars already do reminders.
- A database. Registers are files in the matter folder.
