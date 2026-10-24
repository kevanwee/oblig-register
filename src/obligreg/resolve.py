"""Resolve triggers into dates. Pure; every result carries a trace.

Business-day arithmetic needs a jurisdiction calendar. We accept anything with
`add_working_days(date, n) -> date` (sg-deadline's Calendar satisfies this). Without one,
business-day obligations are reported as unresolved rather than approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from dateutil.relativedelta import relativedelta

from .calendars import contract_calendar
from .models import Freq, Obligation, Register


class WorkingDayCalendar(Protocol):
    def add_working_days(self, d: date, n: int) -> date: ...


@dataclass
class Resolved:
    obligation: Obligation
    deadline: date | None
    occurrences: list[date] = field(default_factory=list)  # recurring only
    trace: list[str] = field(default_factory=list)
    unresolved_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.deadline is not None or bool(self.occurrences)


_STEP = {Freq.WEEKLY: relativedelta(weeks=1), Freq.MONTHLY: relativedelta(months=1),
         Freq.QUARTERLY: relativedelta(months=3), Freq.ANNUAL: relativedelta(years=1)}


def _anchor_date(reg: Register, anchor: str, done: dict[str, Resolved]) -> tuple[date | None, str]:
    if anchor == "effective_date":
        return reg.effective_date, "effective date"
    if anchor == "expiry":
        return reg.expiry, "expiry"
    if anchor.startswith("event:"):
        name = anchor[6:]
        return reg.events.get(name), f"event '{name}'"
    r = done.get(anchor)
    if r is None or r.deadline is None:
        return None, f"obligation {anchor}"
    return r.deadline, f"deadline of {anchor}"


def _resolve_one(reg: Register, o: Obligation, done: dict[str, Resolved],
                 cal: WorkingDayCalendar | None, horizon: date | None) -> Resolved:
    t = o.trigger
    trace = [f"{o.id}: {o.description}", f"clause {o.clause_ref}: \"{o.verbatim}\""]

    if t.kind == "fixed":
        trace.append(f"fixed date {t.date}")
        return Resolved(o, t.date, trace=trace)

    if t.kind == "event":
        d = reg.events.get(t.event or "")
        if d is None:
            return Resolved(o, None, trace=trace,
                            unresolved_reason=f"event '{t.event}' has no date yet "
                                              "(add it under `events:` when it happens)")
        trace.append(f"event '{t.event}' occurred {d}")
        return Resolved(o, d, trace=trace)

    if t.kind == "relative":
        rel = t.relative
        base, label = _anchor_date(reg, rel.anchor, done)
        if base is None:
            return Resolved(o, None, trace=trace,
                            unresolved_reason=f"anchor {label} is not dated")
        sign = 1 if rel.direction == "after" else -1
        trace.append(f"anchor {label}: {base}")
        if rel.months:
            d = base + relativedelta(months=sign * rel.months)
            trace.append(f"{'+' if sign > 0 else '-'} {rel.months} month(s) = {d}")
        elif rel.days:
            d = base + timedelta(days=sign * rel.days)
            trace.append(f"{'+' if sign > 0 else '-'} {rel.days} calendar day(s) = {d}")
        else:
            if cal is None:
                return Resolved(o, None, trace=trace,
                                unresolved_reason="business-day period but no working-day "
                                                  "calendar matching the contract "
                                                  "definition supplied")
            d = cal.add_working_days(base, sign * rel.business_days)
            trace.append(f"{'+' if sign > 0 else '-'} {rel.business_days} business day(s) = {d}")
        return Resolved(o, d, trace=trace)

    # recurring
    rc = t.recurrence
    start = rc.start or reg.effective_date
    until = rc.until or reg.expiry or horizon
    if start is None:
        return Resolved(o, None, trace=trace, unresolved_reason="recurrence has no start "
                                                                "(set start or effective_date)")
    if until is None:
        return Resolved(o, None, trace=trace, unresolved_reason="recurrence has no end "
                                                                "(set until, expiry, or a horizon)")
    if rc.day_of_month:
        start = start.replace(day=rc.day_of_month)
        if start < (rc.start or reg.effective_date):
            start += relativedelta(months=1)
    occ = []
    cur = start
    while cur <= until:
        occ.append(cur)
        cur += _STEP[rc.freq]
    trace.append(f"{rc.freq.value} from {start} until {until}: {len(occ)} occurrence(s)")
    return Resolved(o, occ[0] if occ else None, occurrences=occ, trace=trace)


def resolve(reg: Register, cal: WorkingDayCalendar | None = None,
            *, horizon: date | None = None) -> list[Resolved]:
    """Resolve every obligation. Relative anchors to other obligations are resolved in
    dependency order (iteratively; cycles end up unresolved)."""
    cal = contract_calendar(reg.business_day_rule, cal)
    done: dict[str, Resolved] = {}
    pending = list(reg.obligations)
    progress = True
    while pending and progress:
        progress = False
        for o in list(pending):
            rel = o.trigger.relative
            if rel and rel.anchor in {p.id for p in pending} and rel.anchor != o.id:
                continue  # wait for the anchor
            done[o.id] = _resolve_one(reg, o, done, cal, horizon)
            pending.remove(o)
            progress = True
    for o in pending:  # cycles
        done[o.id] = Resolved(o, None, trace=[f"{o.id}"],
                              unresolved_reason="circular anchor reference")
    return [done[o.id] for o in reg.obligations]
