import json
from datetime import date

import pytest
from scenarios import create

from obligreg.amendment_models import AmendmentPlan, Decision
from obligreg.amendment_package import apply, build, inputs
from obligreg.amendments import analyze, candidate
from obligreg.calendars import FrozenCalendar
from obligreg.models import json_schema


def decision(tmp_path, package, *, outcome="approved"):
    body = package["payload"]
    value = Decision(
        package_digest=package["digest"],
        outcome=outcome,
        actor="Synthetic supervising lawyer",
        evidence="Synthetic review of every change and trace.",
        reviewed_at="2027-01-06T12:00:00+08:00",
        synthetic=True,
        changes={c["id"]: "accept" for c in body["plan"]["changes"]},
        impacts_acknowledged=[i["id"] for i in body["analysis"]["impacts"] if i["impacted"]],
    )
    path = tmp_path / "decision.json"
    path.write_text(value.model_dump_json(), encoding="utf-8")
    return path


def test_renewal_transitive_dates_and_recurrences(tmp_path):
    base, plan = create(tmp_path)
    package = build(base, plan, tmp_path / "review")
    rows = {r["id"]: r for r in package["payload"]["analysis"]["impacts"]}
    assert rows["renewal-notice"]["before_dates"]["deadline"] == "2027-04-01"
    assert rows["renewal-notice"]["after_dates"]["deadline"] == "2027-11-01"
    assert rows["escalation"]["before_dates"]["deadline"] == "2027-03-18"
    assert rows["escalation"]["after_dates"]["deadline"] == "2027-10-18"
    assert len(rows["report"]["before_dates"]["occurrences"]) == 6
    assert len(rows["report"]["after_dates"]["occurrences"]) == 12
    assert not package["payload"]["analysis"]["blockers"]
    original = base.read_bytes()
    apply(tmp_path / "review", base, plan, decision(tmp_path, package), tmp_path / "v2")
    assert base.read_bytes() == original
    assert (tmp_path / "v2/calendar.ics").exists()
    assert (
        "service-agreement-renewal-notice@oblig-register"
        in (tmp_path / "v2/calendar.ics").read_text()
    )


def test_business_day_definition_propagates(tmp_path):
    base, plan = create(tmp_path, "business-day")
    package = build(base, plan, tmp_path / "review")
    rows = {r["id"]: r for r in package["payload"]["analysis"]["impacts"]}
    assert rows["insurance"]["before_dates"]["deadline"] == "2027-01-07"
    assert rows["insurance"]["after_dates"]["deadline"] == "2027-01-08"
    assert rows["followup"]["before_dates"]["deadline"] == "2027-01-10"
    assert rows["followup"]["after_dates"]["deadline"] == "2027-01-11"


def test_ambiguity_blocks_approval_but_allows_rejection(tmp_path):
    base, plan = create(tmp_path, "ambiguous")
    package = build(base, plan, tmp_path / "review")
    assert len(package["payload"]["analysis"]["blockers"]) >= 3
    with pytest.raises(ValueError, match="blockers"):
        apply(tmp_path / "review", base, plan, decision(tmp_path, package), tmp_path / "v2")
    assert not (tmp_path / "v2").exists()
    apply(
        tmp_path / "review",
        base,
        plan,
        decision(tmp_path, package, outcome="rejected"),
        tmp_path / "refused",
    )
    assert sorted(p.name for p in (tmp_path / "refused").iterdir()) == [
        "decision.json",
        "receipt.json",
    ]


@pytest.mark.parametrize("target", ["base", "plan", "source", "html", "package", "snapshot"])
def test_tampering_or_stale_input_fails(tmp_path, target):
    base, plan = create(tmp_path)
    directory = tmp_path / "review"
    package = build(base, plan, directory)
    d = decision(tmp_path, package)
    paths = {
        "base": base,
        "plan": plan,
        "source": tmp_path / "agreement.txt",
        "html": directory / "review.html",
        "package": directory / "review.json",
        "snapshot": directory / "sources/agreement.txt",
    }
    with paths[target].open("ab") as stream:
        stream.write(b" ")
    # JSON whitespace alone preserves semantics; raw input hashes still detect it.
    if target == "package":
        data = json.loads(paths[target].read_bytes())
        data["payload"]["analysis"]["blockers"] = ["modified"]
        paths[target].write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        apply(directory, base, plan, d, tmp_path / "v2")
    assert not (tmp_path / "v2").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("changes", {}),
        ("changes", {"extend-term": "accept", "shorten-notice": "defer"}),
        ("impacts_acknowledged", []),
        ("package_digest", "0" * 64),
        ("synthetic", False),
    ],
)
def test_incomplete_or_wrong_decision_fails(tmp_path, field, value):
    base, plan = create(tmp_path)
    package = build(base, plan, tmp_path / "review")
    path = decision(tmp_path, package)
    data = json.loads(path.read_bytes())
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        apply(tmp_path / "review", base, plan, path, tmp_path / "v2")


@pytest.mark.parametrize("mutation", ["quote", "span", "coverage", "before", "extra", "anchor"])
def test_bad_proposals_fail(tmp_path, mutation):
    base_path, plan_path = create(tmp_path)
    base, plan, docs, _ = inputs(base_path, plan_path)
    value = plan.model_dump(mode="json")
    if mutation == "quote":
        value["baseline"]["report"]["quote"] = "Wrong wording"
    elif mutation == "span":
        value["changes"][0]["evidence"][0]["end"] -= 1
    elif mutation == "coverage":
        value["sections"].pop()
        value["changes"].pop()
    elif mutation == "before":
        value["changes"][0]["before"] = "2020-01-01"
    elif mutation == "extra":
        value["changes"][1]["after"]["trigger"]["relative"]["typo"] = 6
    else:
        value["changes"][1]["after"]["trigger"]["relative"]["anchor"] = "missing"
    with pytest.raises(ValueError):
        analyze(base, AmendmentPlan.model_validate(value), docs)


def test_frozen_calendar_refuses_missing_year():
    cal = FrozenCalendar({"jurisdiction": "SG", "years": {}})
    with pytest.raises(ValueError, match="2027"):
        cal.add_working_days(date(2026, 12, 31), 1)


def test_output_is_never_overwritten(tmp_path):
    base, plan = create(tmp_path)
    package = build(base, plan, tmp_path / "review")
    d = decision(tmp_path, package)
    apply(tmp_path / "review", base, plan, d, tmp_path / "v2")
    with pytest.raises(ValueError, match="already exists"):
        apply(tmp_path / "review", base, plan, d, tmp_path / "v2")


def test_amendment_schemas_are_current():
    from pathlib import Path

    root = Path(__file__).parents[1] / "schema"
    for filename, model in [
        ("amendment.schema.json", AmendmentPlan),
        ("decision.schema.json", Decision),
    ]:
        assert json.loads((root / filename).read_text()) == model.model_json_schema()
    assert json.loads((root / "register.schema.json").read_text()) == json_schema()


def test_removal_requires_repairing_dependents(tmp_path):
    bp, pp = create(tmp_path)
    base, plan, _, _ = inputs(bp, pp)
    raw = plan.model_dump(mode="json")
    raw["changes"] = [{**raw["changes"][1], "kind": "remove", "after": None}]
    with pytest.raises(ValueError, match="anchor"):
        candidate(base, AmendmentPlan.model_validate(raw))
