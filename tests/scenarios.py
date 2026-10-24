"""Explicit synthetic proposals. This authors fixtures; it does not interpret text."""

import json
from pathlib import Path

import yaml

from obligreg.amendment_models import AmendmentPlan
from obligreg.amendments import sha
from obligreg.models import Register


def create(directory: Path, scenario="renewal"):
    directory.mkdir(parents=True, exist_ok=True)
    notice = "Customer must give non-renewal notice ninety days before expiry."
    escalation = (
        "Supplier must send an escalation fourteen days before the non-renewal notice deadline."
    )
    reporting = "Supplier must provide a report monthly from the effective date until expiry."
    insurance = (
        "Supplier must provide insurance evidence two Business Days after the effective date."
    )
    followup = "Customer must review insurance evidence three days after its delivery deadline."
    definition = "Business Day means Monday to Friday, including public holidays."
    base = {
        "contract": "Service agreement",
        "parties": ["Customer", "Supplier"],
        "effective_date": "2027-01-01",
        "expiry": "2027-06-30",
        "obligations": [],
    }

    def obligation(oid, wording, category, trigger, obligor="Supplier"):
        return {
            "id": oid,
            "obligor": obligor,
            "obligee": "Customer" if obligor == "Supplier" else "Supplier",
            "category": category,
            "description": wording,
            "clause_ref": oid,
            "verbatim": wording,
            "trigger": trigger,
        }

    def relative(anchor, n, unit="days", direction="before"):
        return {"kind": "relative", "relative": {"anchor": anchor, unit: n, "direction": direction}}

    if scenario == "renewal":
        base["obligations"] = [
            obligation("renewal-notice", notice, "renewal", relative("expiry", 90), "Customer"),
            obligation("escalation", escalation, "notice", relative("renewal-notice", 14)),
            obligation(
                "report",
                reporting,
                "reporting",
                {"kind": "recurring", "recurrence": {"freq": "monthly"}},
            ),
        ]
        amendment_lines = [
            "The expiry date is changed to 31 December 2027.",
            "Customer must give non-renewal notice sixty days before expiry.",
        ]
    else:
        base["effective_date"] = "2027-01-05"
        base["business_day_rule"] = {
            "kind": "explicit",
            "clause_ref": "definition",
            "verbatim": definition,
        }
        base["obligations"] = [
            obligation(
                "insurance",
                insurance,
                "insurance",
                relative("effective_date", 2, "business_days", "after"),
            ),
            obligation(
                "followup", followup, "compliance", relative("insurance", 3, "days", "after")
            ),
        ]
        amendment_lines = [
            "Business Day means Monday to Friday, including public holidays, "
            "but excludes 7 January 2027."
        ]
        if scenario == "ambiguous":
            amendment_lines = ["Business Day means a day on which the relevant banks are open."]
    base = Register.model_validate(base)
    agreement = (
        "\n".join(
            [o.verbatim for o in base.obligations]
            + ([definition] if base.business_day_rule else [])
        )
        + "\n"
    )
    amendment = "\n".join(amendment_lines) + "\n"
    for name, text in (("agreement", agreement), ("amendment", amendment)):
        (directory / f"{name}.txt").write_bytes(text.encode())

    def ref(document, text, quote):
        start = text.index(quote)
        return {
            "document": document,
            "start": start,
            "end": start + len(quote),
            "quote": quote,
            "locator": f"{document} paragraph at character {start}",
        }

    references = [ref("amendment", amendment, line) for line in amendment_lines]
    raw = base.model_dump(mode="json")
    if scenario == "renewal":
        changed = json.loads(json.dumps(raw["obligations"][0]))
        changed["verbatim"] = amendment_lines[1]
        changed["description"] = "Give non-renewal notice sixty days before expiry"
        changed["trigger"]["relative"]["days"] = 60
        changes = [
            {
                "id": "extend-term",
                "kind": "field",
                "target": "expiry",
                "before": raw["expiry"],
                "after": "2027-12-31",
                "rationale": "The amendment expressly replaces the expiry date.",
                "evidence": [references[0]],
            },
            {
                "id": "shorten-notice",
                "kind": "replace",
                "target": "renewal-notice",
                "before": raw["obligations"][0],
                "after": changed,
                "rationale": "The operative replacement changes ninety to sixty days.",
                "evidence": [references[1]],
            },
        ]
    else:
        rule = dict(
            raw["business_day_rule"], verbatim=amendment_lines[0], excluded_dates=["2027-01-07"]
        )
        if scenario == "ambiguous":
            rule.update(
                kind="unresolved", excluded_dates=[], notes=["Relevant banks not identified"]
            )
        changes = [
            {
                "id": "change-business-day",
                "kind": "field",
                "target": "business_day_rule",
                "before": raw["business_day_rule"],
                "after": rule,
                "rationale": "Apply the amended definition to all Business Day periods.",
                "evidence": references,
            }
        ]
    plan = {
        "title": f"Service agreement — {scenario} amendment",
        "as_of": "2027-01-06",
        "effective_on": "2027-01-06",
        "execution_status": "confirmed",
        "effect_basis": "Synthetic scenario assumes execution and effectiveness on 6 January 2027.",
        "sources": [
            {
                "id": name,
                "role": name,
                "path": f"{name}.txt",
                "sha256": sha((directory / f"{name}.txt").read_bytes()),
            }
            for name in ("agreement", "amendment")
        ],
        "baseline": {o.id: ref("agreement", agreement, o.verbatim) for o in base.obligations},
        "sections": [
            {
                "id": f"section-{i}",
                "evidence": reference,
                "disposition": "change",
                "changes": [changes[i]["id"]],
                "reason": "This paragraph supplies the proposed operative change.",
            }
            for i, reference in enumerate(references)
        ],
        "changes": changes,
        "questions": [],
        "synthetic": True,
    }
    if base.business_day_rule:
        plan["baseline_business_day_rule"] = ref("agreement", agreement, definition)
    if scenario == "ambiguous":
        plan["questions"] = [
            {
                "id": "which-banks",
                "question": "Which banks and locations govern?",
                "evidence": references,
            }
        ]
        plan.update(execution_status="unconfirmed", effective_on=None)
    plan = AmendmentPlan.model_validate(plan)
    (directory / "base.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    (directory / "proposal.json").write_text(
        plan.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return directory / "base.yaml", directory / "proposal.json"
