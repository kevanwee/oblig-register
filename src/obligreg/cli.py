"""CLI: validate, schema, resolve, render, ics, upcoming."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from .ics import to_ics
from .models import json_schema, load_register
from .render import render_markdown, upcoming
from .resolve import resolve


def _load(path: Path):
    try:
        return load_register(path)
    except ValidationError as e:
        print(f"invalid register {path}:\n{e}", file=sys.stderr)
        sys.exit(2)


def _calendar(jurisdiction: str | None):
    if not jurisdiction:
        return None
    try:
        from sg_deadline import load_calendar
    except ImportError:
        print("warning: --jurisdiction needs sg-deadline (pip install sg-deadline); "
              "business-day obligations will be unresolved", file=sys.stderr)
        return None
    return load_calendar(jurisdiction)


def cmd_validate(a):
    for p in a.register:
        r = _load(p)
        print(f"ok  {p}  ({r.contract}, {len(r.obligations)} obligations)")
    return 0


def cmd_schema(a):
    print(json.dumps(json_schema(), indent=2))
    return 0


def cmd_resolve(a):
    reg = _load(a.register)
    res = resolve(reg, _calendar(a.jurisdiction), horizon=a.horizon)
    for r in res:
        print("\n".join(r.trace))
        print(f"  => {r.deadline}" if r.resolved else f"  => UNRESOLVED: {r.unresolved_reason}")
        print()
    n = sum(1 for r in res if not r.resolved)
    return 1 if (n and a.strict) else 0


def cmd_render(a):
    reg = _load(a.register)
    print(render_markdown(resolve(reg, _calendar(a.jurisdiction), horizon=a.horizon), reg))
    return 0


def cmd_ics(a):
    reg = _load(a.register)
    ics = to_ics(resolve(reg, _calendar(a.jurisdiction), horizon=a.horizon), reg)
    if a.output:
        a.output.write_text(ics, encoding="utf-8", newline="")
        print(f"wrote {a.output}")
    else:
        sys.stdout.write(ics)
    return 0


def cmd_upcoming(a):
    reg = _load(a.register)
    res = resolve(reg, _calendar(a.jurisdiction), horizon=a.horizon)
    for d, r in upcoming(res, as_of=a.as_of, days=a.days):
        o = r.obligation
        print(f"{d}  {o.obligor:20} {o.description}  (cl {o.clause_ref})")
    return 0


def cmd_amend_build(a):
    from .amendment_package import build, inputs
    from .amendments import analyze

    snapshot = None
    if a.jurisdiction:
        if a.jurisdiction != "SG":
            raise ValueError("Automatic calendar preparation currently supports SG only")
        try:
            from sg_deadline.calendar_store import CalendarStore
            from sg_deadline.preparation import prepare
        except ImportError as exc:
            raise ValueError("Install sg-deadline 0.2+ for official calendar preparation") from exc
        base, plan, documents, hashes = inputs(a.base, a.plan)
        try:
            prepared = prepare(
                lambda cal: analyze(base, plan, documents, cal, horizon=a.horizon),
                store=CalendarStore(a.calendar_cache) if a.calendar_cache else CalendarStore(),
                offline=a.offline, identity=hashes)
        except LookupError as exc:
            raise ValueError(f"Calendar preparation failed: {exc}. "
                             "No review was published.") from exc
        snapshot = {"jurisdiction": "SG", "weekend": list(prepared.calendar.weekend),
                    "years": prepared.receipt["calendars"], "warnings": prepared.warnings}
    package = build(a.base, a.plan, a.out, calendar=snapshot, horizon=a.horizon)
    print(f"Review {package['digest']}\nOpen {a.out / 'review.html'}")
    print(f"{len(package['payload']['analysis']['blockers'])} approval blocker(s)")
    return 0


def cmd_amend_apply(a):
    from .amendment_package import apply

    outcome = apply(a.review, a.base, a.plan, a.decision, a.out)
    print(f"Recorded {outcome}: {a.out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="obligreg", description="Contract obligations as data.")
    p.add_argument("--jurisdiction", "-j", help="e.g. SG; enables business-day arithmetic")
    p.add_argument("--horizon", type=date.fromisoformat,
                   help="end date for open-ended recurrences (default: register expiry)")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate")
    v.add_argument("register", type=Path, nargs="+")
    v.set_defaults(fn=cmd_validate)

    s = sub.add_parser("schema")
    s.set_defaults(fn=cmd_schema)

    r = sub.add_parser("resolve", help="print every deadline with its trace")
    r.add_argument("register", type=Path)
    r.add_argument("--strict", action="store_true", help="exit 1 if anything is unresolved")
    r.set_defaults(fn=cmd_resolve)

    m = sub.add_parser("render", help="markdown register")
    m.add_argument("register", type=Path)
    m.set_defaults(fn=cmd_render)

    i = sub.add_parser("ics", help="calendar export")
    i.add_argument("register", type=Path)
    i.add_argument("-o", "--output", type=Path)
    i.set_defaults(fn=cmd_ics)

    u = sub.add_parser("upcoming")
    u.add_argument("register", type=Path)
    u.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    u.add_argument("--days", type=int, default=90)
    u.set_defaults(fn=cmd_upcoming)

    amend = sub.add_parser("amend", help="source-backed amendment impact review")
    actions = amend.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", help="freeze inputs and create a local review")
    build.add_argument("--base", type=Path, required=True)
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--calendar-cache", type=Path)
    build.add_argument("--offline", action="store_true")
    build.set_defaults(fn=cmd_amend_build)
    apply = actions.add_parser("apply", help="validate the decision and publish a new version")
    apply.add_argument("--base", type=Path, required=True)
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--review", type=Path, required=True)
    apply.add_argument("--decision", type=Path, required=True)
    apply.add_argument("--out", type=Path, required=True)
    apply.set_defaults(fn=cmd_amend_apply)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
