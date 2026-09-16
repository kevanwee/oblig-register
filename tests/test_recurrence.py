from datetime import date

import pytest
from pydantic import ValidationError

from obligreg import Register, resolve, to_ics
from obligreg.models import Relative, Trigger


def test_month_end_dates_match_export():
    register = Register(contract="Example", parties=["A", "B"], obligations=[{
        "id": "report", "obligor": "A", "obligee": "B", "description": "Deliver the report",
        "clause_ref": "4", "verbatim": "A shall deliver a monthly report.",
        "trigger": {"kind": "recurring", "recurrence": {
            "freq": "monthly", "start": "2026-01-31", "until": "2026-04-30"}},
    }])
    result = resolve(register)
    assert result[0].occurrences == [date(2026, 1, 31), date(2026, 2, 28),
                                     date(2026, 3, 31), date(2026, 4, 30)]
    exported = to_ics(result, register)
    assert "RDATE;VALUE=DATE:20260228,20260331,20260430" in exported
    assert "RRULE" not in exported


def test_negative_periods_and_mixed_triggers_are_rejected():
    with pytest.raises(ValidationError):
        Relative(anchor="expiry", days=-30)
    with pytest.raises(ValidationError):
        Trigger(kind="fixed", date="2026-01-01", event="termination")
