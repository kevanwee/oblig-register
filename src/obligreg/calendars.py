"""Contract calendar policies and portable snapshots. No network or legal inference."""

from __future__ import annotations

from datetime import date, timedelta

from .models import BusinessDayRule


class FrozenCalendar:
    def __init__(self, snapshot: dict):
        self.snapshot = snapshot
        self.jurisdiction = snapshot["jurisdiction"]
        self.weekend = tuple(snapshot.get("weekend", [5, 6]))

    def add_working_days(self, start: date, n: int) -> date:
        current, remaining, step = start, abs(n), 1 if n >= 0 else -1
        while remaining:
            current += timedelta(days=step)
            year = self.snapshot["years"].get(str(current.year))
            if year is None:
                raise ValueError(f"Frozen calendar has no coverage for {current.year}")
            excluded = {h["date"] for h in year["calendar"]["holidays"]}
            if current.weekday() not in self.weekend and current.isoformat() not in excluded:
                remaining -= 1
        return current


class ContractCalendar:
    def __init__(self, rule: BusinessDayRule, base=None):
        self.rule, self.base = rule, base

    def add_working_days(self, start: date, n: int) -> date:
        current, remaining, step = start, abs(n), 1 if n >= 0 else -1
        while remaining:
            current = (
                self.base.add_working_days(current, step)
                if self.base
                else current + timedelta(days=step)
            )
            if (
                current.weekday() not in self.rule.weekend_days
                and current not in self.rule.excluded_dates
            ):
                remaining -= 1
        return current


def contract_calendar(rule: BusinessDayRule | None, base):
    if rule is None:
        return base
    if rule.kind == "explicit":
        return ContractCalendar(rule)
    if rule.kind == "unresolved":
        return None
    if (
        base is None
        or getattr(base, "jurisdiction", None) != rule.jurisdiction
        or set(getattr(base, "weekend", ())) != set(rule.weekend_days)
    ):
        return None
    return ContractCalendar(rule, base)
