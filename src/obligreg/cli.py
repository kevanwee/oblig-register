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

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
