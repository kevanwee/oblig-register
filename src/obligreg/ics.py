"""RFC 5545 export. Hand-rolled on purpose: the subset we need is small and a dependency
would be larger than this file."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .models import Freq, Register
from .resolve import Resolved

_RRULE = {Freq.WEEKLY: "FREQ=WEEKLY", Freq.MONTHLY: "FREQ=MONTHLY",
          Freq.QUARTERLY: "FREQ=MONTHLY;INTERVAL=3", Freq.ANNUAL: "FREQ=YEARLY"}


def _esc(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold at 75 octets per RFC 5545 s 3.1."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 75:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _d(d: date) -> str:
    return d.strftime("%Y%m%d")


def to_ics(resolved: list[Resolved], reg: Register, *,
           prodid: str = "-//oblig-register//EN") -> str:
    slug = _slug(reg.contract)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{prodid}", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_esc(reg.contract)} obligations"]
    for r in resolved:
        if not r.resolved:
            continue
        o = r.obligation
        start = r.occurrences[0] if r.occurrences else r.deadline
        desc = (f"Clause {o.clause_ref}\n\"{o.verbatim}\"\n\nObligor: {o.obligor}\n"
                f"Obligee: {o.obligee}")
        if o.condition:
            desc += f"\nCondition: {o.condition}"
        if o.consequence:
            desc += f"\nConsequence: {o.consequence}"
        desc += "\n\n" + "\n".join(r.trace)
        ev = [
            "BEGIN:VEVENT",
            f"UID:{slug}-{o.id}@oblig-register",
            f"DTSTAMP:{_d(date.today())}T000000Z",
            f"DTSTART;VALUE=DATE:{_d(start)}",
            f"DTEND;VALUE=DATE:{_d(start + timedelta(days=1))}",
            f"SUMMARY:{_esc(f'[{reg.contract}] {o.description}')}",
            f"DESCRIPTION:{_esc(desc)}",
            f"CATEGORIES:{o.category.value.upper()}",
        ]
        if r.occurrences and o.trigger.recurrence:
            rc = o.trigger.recurrence
            if start.day <= 28:
                ev.append(f"RRULE:{_RRULE[rc.freq]};UNTIL={_d(r.occurrences[-1])}")
            elif len(r.occurrences) > 1:
                ev.append("RDATE;VALUE=DATE:" + ",".join(_d(d) for d in r.occurrences[1:]))
        if o.lead_days:
            ev += ["BEGIN:VALARM", "ACTION:DISPLAY",
                   f"DESCRIPTION:{_esc(o.description)}",
                   f"TRIGGER:-P{o.lead_days}D", "END:VALARM"]
        ev.append("END:VEVENT")
        lines += ev
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
