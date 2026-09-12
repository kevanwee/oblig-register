"""Markdown views of a resolved register."""

from __future__ import annotations

from datetime import date, timedelta

from .models import Register
from .resolve import Resolved


def render_markdown(resolved: list[Resolved], reg: Register) -> str:
    out = [f"# Obligations register: {reg.contract}", "",
           f"Parties: {', '.join(reg.parties)}"]
    if reg.effective_date:
        expiry = f"; expiry: {reg.expiry}" if reg.expiry else ""
        out.append(f"Effective: {reg.effective_date}{expiry}")
    if reg.governing_law:
        out.append(f"Governing law: {reg.governing_law}")
    out += ["", "| Deadline | Obligor | Category | Obligation | Clause | Consequence |",
            "|---|---|---|---|---|---|"]
    dated = sorted((r for r in resolved if r.resolved), key=lambda r: r.deadline)
    for r in dated:
        o = r.obligation
        when = r.deadline.isoformat()
        if r.occurrences:
            when += f" (then {o.trigger.recurrence.freq.value}, {len(r.occurrences)}x)"
        out.append(f"| {when} | {o.obligor} | {o.category.value} | {o.description} | "
                   f"{o.clause_ref} | {o.consequence or ''} |")
    unresolved = [r for r in resolved if not r.resolved]
    if unresolved:
        out += ["", "## Not yet dated", ""]
        for r in unresolved:
            o = r.obligation
            out.append(f"- **{o.description}** (clause {o.clause_ref}, {o.obligor}): "
                       f"{r.unresolved_reason}")
    if reg.notice_clause:
        nc = reg.notice_clause
        out += ["", f"## Notices (clause {nc.clause_ref})", "", f"> {nc.verbatim}", ""]
        for party, addr in nc.addresses.items():
            out.append(f"- {party}: {addr}")
        if nc.methods:
            out += ["", "| Method | Deemed received |", "|---|---|"]
            for m in nc.methods:
                unit = "business day(s)" if m.business_days else "day(s)"
                rule = f"+{m.offset_days} {unit}" if m.offset_days else "same day"
                if m.cutoff:
                    rule += f", cutoff {m.cutoff.strftime('%H:%M')}"
                out.append(f"| {m.method} | {rule} |")
    return "\n".join(out)


def upcoming(resolved: list[Resolved], *, as_of: date, days: int) -> list[tuple[date, Resolved]]:
    """(date, resolved) pairs falling within [as_of, as_of + days], recurrences expanded."""
    end = as_of + timedelta(days=days)
    out = []
    for r in resolved:
        dates = r.occurrences or ([r.deadline] if r.deadline else [])
        for d in dates:
            if as_of <= d <= end:
                out.append((d, r))
    return sorted(out, key=lambda p: p[0])
