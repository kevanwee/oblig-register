import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from obligreg import Register, load_register, render_markdown, resolve, to_ics, upcoming
from obligreg.cli import main
from obligreg.models import json_schema

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "sample-register.yaml"


class WeekdayCalendar:
    """Minimal working-day calendar (weekends only) so tests do not need sg-deadline."""

    def add_working_days(self, d: date, n: int) -> date:
        step = 1 if n >= 0 else -1
        left = abs(n)
        while left:
            d += timedelta(days=step)
            if d.weekday() < 5:
                left -= 1
        return d


@pytest.fixture
def reg():
    return load_register(SAMPLE)


def test_sample_validates(reg):
    assert len(reg.obligations) == 8
    assert reg.notice_clause and len(reg.notice_clause.methods) == 3


def test_schema_file_matches_model():
    committed = json.loads((ROOT / "schema" / "register.schema.json").read_text("utf-8"))
    assert committed == json_schema(), "run: obligreg schema > schema/register.schema.json"


def test_validation_errors(reg):
    raw = reg.model_dump(mode="json")
    raw["obligations"][0]["obligor"] = "Nobody"
    with pytest.raises(ValidationError, match="not a party"):
        Register.model_validate(raw)

    raw = reg.model_dump(mode="json")
    raw["obligations"][5]["trigger"]["relative"]["anchor"] = "no-such-id"
    with pytest.raises(ValidationError, match="not an obligation id"):
        Register.model_validate(raw)

    raw = reg.model_dump(mode="json")
    raw["obligations"][0]["verbatim"] = "short"
    with pytest.raises(ValidationError):
        Register.model_validate(raw)

    raw = reg.model_dump(mode="json")
    raw["obligations"][2]["trigger"]["relative"]["days"] = 3  # now both days and business_days
    with pytest.raises(ValidationError, match="exactly one"):
        Register.model_validate(raw)


def test_resolve_dates(reg):
    res = {r.obligation.id: r for r in resolve(reg, WeekdayCalendar())}
    # 90 days before 2029-02-28 = 2028-11-30
    assert res["non-renewal-notice"].deadline == date(2028, 11, 30)
    assert res["price-review"].deadline == date(2028, 10, 31)
    # 14 weekdays after Sun 2026-03-01 -> Mon 2 Mar is day 1 ... Thu 19 Mar is day 14
    assert res["insurance-certificate"].deadline == date(2026, 3, 19)
    # annual recurrence: 2026, 2027, 2028 (2029-03-01 is past expiry)
    assert res["annual-fee"].occurrences == [date(2026, 3, 1), date(2027, 3, 1), date(2028, 3, 1)]
    # monthly on the 7th starting from effective date
    assert res["sla-report"].occurrences[0] == date(2026, 3, 7)
    assert len(res["sla-report"].occurrences) == 36
    # event-anchored chain: unresolved until the event is dated
    assert not res["data-return"].resolved
    assert "termination" in res["data-return"].unresolved_reason
    assert not res["data-deletion"].resolved
    assert not res["breach-notification"].resolved


def test_event_dated_resolves_chain(reg):
    reg.events["termination"] = date(2027, 6, 30)
    res = {r.obligation.id: r for r in resolve(reg, WeekdayCalendar())}
    assert res["data-return"].deadline == date(2027, 7, 30)
    assert res["data-deletion"].deadline == date(2027, 8, 29)
    assert any("deadline of data-return" in line for line in res["data-deletion"].trace)


def test_business_days_without_calendar_is_unresolved(reg):
    res = {r.obligation.id: r for r in resolve(reg, None)}
    assert not res["insurance-certificate"].resolved
    assert "calendar" in res["insurance-certificate"].unresolved_reason


def test_ics_output(reg):
    ics = to_ics(resolve(reg, WeekdayCalendar()), reg)
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert "RRULE:FREQ=YEARLY;UNTIL=20280301" in ics
    assert "RRULE:FREQ=MONTHLY;UNTIL=" in ics
    assert "TRIGGER:-P45D" in ics  # non-renewal lead time
    assert "UID:acme-beta-msa-2026-annual-fee@oblig-register" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert "data-return" not in ics  # unresolved obligations are not exported


def test_render_and_upcoming(reg):
    res = resolve(reg, WeekdayCalendar())
    md = render_markdown(res, reg)
    assert "## Not yet dated" in md and "## Notices (clause 21)" in md
    assert "| email | +1 business day(s), cutoff 17:00 |" in md
    up = upcoming(res, as_of=date(2028, 10, 1), days=90)
    ids = [r.obligation.id for _, r in up]
    assert ids[:2] == ["sla-report", "sla-report"] or "price-review" in ids
    assert "price-review" in ids and "non-renewal-notice" in ids


def test_cli(capsys):
    assert main(["validate", str(SAMPLE)]) == 0
    assert main(["resolve", str(SAMPLE), "--strict"]) == 1  # event-anchored items unresolved
    assert main(["render", str(SAMPLE)]) == 0
    assert main(["ics", str(SAMPLE)]) == 0
    assert "BEGIN:VEVENT" in capsys.readouterr().out


sg = pytest.importorskip("sg_deadline", reason="optional integration with sg-deadline")


def test_with_sg_deadline_calendar(reg):
    cal = sg.load_calendar("SG")
    res = {r.obligation.id: r for r in resolve(reg, cal)}
    # 14 SG working days after Sun 1 Mar 2026: no public holidays in that window -> 19 Mar
    assert res["insurance-certificate"].deadline == date(2026, 3, 19)
