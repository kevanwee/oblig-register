"""Validate an explicit legal proposal and calculate its mechanical consequences.

No clause extraction or legal interpretation is performed here. Quote checking
proves provenance; the responsible reviewer decides whether the proposal is right.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from .amendment_models import AmendmentPlan, ProposedNotice, ProposedObligation
from .ics import _slug
from .models import Register
from .resolve import resolve

FIELDS = {
    "expiry",
    "effective_date",
    "events",
    "notice_clause",
    "business_day_rule",
    "governing_law",
}


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sources(plan: AmendmentPlan, directory: Path) -> dict:
    result = {}
    for source in plan.sources:
        raw = (directory / source.path).read_bytes()
        if sha(raw) != source.sha256:
            raise ValueError(f"Source {source.id}: bytes changed; create a new review")
        result[source.id] = {
            "text": raw.decode("utf-8-sig"),
            "raw": raw,
            "role": source.role,
            "sha256": source.sha256,
        }
    return result


def check_evidence(ref, documents, role=None):
    document = documents.get(ref.document)
    if document is None or (role and document["role"] != role):
        raise ValueError(f"Evidence {ref.locator}: unknown document or wrong source role")
    if (
        ref.end > len(document["text"])
        or ref.end <= ref.start
        or document["text"][ref.start : ref.end] != ref.quote
    ):
        raise ValueError(f"Evidence {ref.locator}: exact source span does not match")


def validate_evidence(base: Register, plan: AmendmentPlan, documents):
    if set(plan.baseline) != {o.id for o in base.obligations}:
        raise ValueError("Baseline evidence must account for exactly every current obligation")
    for o in base.obligations:
        check_evidence(plan.baseline[o.id], documents, "agreement")
        if plan.baseline[o.id].quote != o.verbatim:
            raise ValueError(f"{o.id}: baseline evidence is not its recorded verbatim quotation")
    for item, ref in (
        (base.notice_clause, plan.baseline_notice),
        (base.business_day_rule, plan.baseline_business_day_rule),
    ):
        if item:
            if ref is None:
                raise ValueError("Provide baseline evidence for the notice/Business Day definition")
            check_evidence(ref, documents, "agreement")
            if ref.quote != item.verbatim:
                raise ValueError("Baseline notice/definition quotation differs from the register")
    changes = {change.id: change for change in plan.changes}
    accounted = set()
    for section in plan.sections:
        check_evidence(section.evidence, documents, "amendment")
        if section.disposition != "change" and section.changes:
            raise ValueError("Only a change section may link proposed changes")
        if section.disposition == "change" and not section.changes:
            raise ValueError("A change section needs its proposed change identifiers")
        for change_id in section.changes:
            if change_id not in changes:
                raise ValueError(f"Section {section.id}: unknown change {change_id}")
            accounted.add(change_id)
    if accounted != set(changes):
        raise ValueError("Every change must be accounted for by an amendment section")
    for document_id, document in documents.items():
        if document["role"] != "amendment":
            continue
        ranges = sorted(
            (s.evidence.start, s.evidence.end)
            for s in plan.sections
            if s.evidence.document == document_id
        )
        cursor = 0
        for start, end in ranges:
            if start < cursor or document["text"][cursor:start].strip():
                raise ValueError("Amendment coverage overlaps or leaves unaccounted text")
            cursor = end
        if document["text"][cursor:].strip():
            raise ValueError("Amendment coverage leaves unaccounted text")
    for change in plan.changes:
        for ref in change.evidence:
            check_evidence(ref, documents, "amendment")
            if not any(
                change.id in section.changes
                and section.evidence.document == ref.document
                and section.evidence.start <= ref.start < ref.end <= section.evidence.end
                for section in plan.sections
            ):
                raise ValueError(f"{change.id}: evidence falls outside its declared section")
    for question in plan.questions:
        for ref in question.evidence:
            check_evidence(ref, documents, "amendment")
    for section in plan.sections:
        if section.disposition == "question" and not any(
            ref.document == section.evidence.document
            and section.evidence.start <= ref.start < ref.end <= section.evidence.end
            for question in plan.questions
            for ref in question.evidence
        ):
            raise ValueError("A question section needs an explicit unresolved question")


def candidate(base: Register, plan: AmendmentPlan) -> Register:
    raw = base.model_dump(mode="json")
    obligations = {o["id"]: o for o in raw["obligations"]}
    order = [o["id"] for o in raw["obligations"]]
    for change in plan.changes:
        if change.kind == "field":
            if change.target not in FIELDS:
                raise ValueError(
                    "Only approved register fields may change; "
                    "contract/party identities stay stable"
                )
            before = raw[change.target]
        else:
            before = obligations.get(change.target)
            if (change.kind == "add") != (before is None):
                raise ValueError(
                    f"{change.id}: add/replace/remove target does not match the baseline"
                )
        if change.before != before:
            raise ValueError(f"{change.id}: before value does not match the frozen baseline")
        if change.kind == "field":
            if change.target == "notice_clause" and change.after is not None:
                ProposedNotice.model_validate(change.after)
            raw[change.target] = change.after
        elif change.kind == "remove":
            if change.after is not None:
                raise ValueError("A removal must have after=null")
            obligations.pop(change.target)
        else:
            after = ProposedObligation.model_validate(change.after)
            if after.id != change.target:
                raise ValueError("Replacement identifiers must remain stable")
            if not any(after.verbatim in ref.quote for ref in change.evidence):
                raise ValueError(
                    "Proposed verbatim must be an actual amendment quotation, "
                    "not reconstructed wording"
                )
            obligations[after.id] = after.model_dump(mode="json")
            if change.kind == "add":
                order.append(after.id)
    raw["obligations"] = [obligations[oid] for oid in order if oid in obligations]
    result = Register.model_validate(raw)
    for obligation in result.obligations:
        if obligation.obligee not in result.parties:
            raise ValueError(f"{obligation.id}: obligee is not a party")
    for change in plan.changes:
        if (
            change.kind == "field"
            and change.target in {"business_day_rule", "notice_clause"}
            and change.after
        ):
            item = getattr(result, change.target)
            if not any(item.verbatim in ref.quote for ref in change.evidence):
                raise ValueError("New notice/definition wording needs an exact amendment quotation")
            if set(change.after) - set(type(item).model_fields):
                raise ValueError("Unknown notice/definition field")
    return result


def dependency_reasons(base: Register, after: Register, plan: AmendmentPlan):
    old, new = {o.id: o for o in base.obligations}, {o.id: o for o in after.obligations}
    reasons = {oid: set() for oid in old.keys() | new.keys()}
    for change in plan.changes:
        if change.kind != "field":
            reasons[change.target].add(f"Direct proposal: {change.id}")
            continue
        for oid in reasons:
            for item in (old.get(oid), new.get(oid)):
                if item is None:
                    continue
                rel, recurrence = item.trigger.relative, item.trigger.recurrence
                field = change.target
                affected = field == "governing_law"
                affected |= field in {"expiry", "effective_date"} and bool(
                    (rel and rel.anchor == field)
                    or (
                        recurrence
                        and (
                            (field == "expiry" and recurrence.until is None)
                            or (field == "effective_date" and recurrence.start is None)
                        )
                    )
                )
                affected |= field == "business_day_rule" and bool(rel and rel.business_days)
                affected |= field == "notice_clause" and item.category.value in {
                    "notice",
                    "renewal",
                }
                if field == "events":
                    name = (
                        item.trigger.event
                        if item.trigger.kind == "event"
                        else (rel.anchor[6:] if rel and rel.anchor.startswith("event:") else None)
                    )
                    affected |= bool(name and base.events.get(name) != after.events.get(name))
                if affected:
                    reasons[oid].add(f"Shared field: {field} ({change.id})")
    progress = True
    while progress:
        progress = False
        for oid in reasons:
            for item in (old.get(oid), new.get(oid)):
                anchor = item.trigger.relative.anchor if item and item.trigger.relative else None
                reason = f"Depends on obligation: {anchor}"
                if anchor in reasons and reasons[anchor] and reason not in reasons[oid]:
                    reasons[oid].add(reason)
                    progress = True
    return reasons


def _waiting(reg, oid, visited=None):
    visited = set() if visited is None else visited
    if oid in visited:
        return False
    visited.add(oid)
    item = reg.by_id(oid)
    if item.trigger.kind == "event":
        return item.trigger.event not in reg.events
    rel = item.trigger.relative
    if rel:
        if rel.anchor.startswith("event:"):
            return rel.anchor[6:] not in reg.events
        if rel.anchor not in {"expiry", "effective_date"}:
            return _waiting(reg, rel.anchor, visited)
    return False


def _resolved(item):
    if item is None:
        return None
    return {
        "deadline": item.deadline.isoformat() if item.deadline else None,
        "occurrences": [d.isoformat() for d in item.occurrences],
        "trace": item.trace,
        "unresolved_reason": item.unresolved_reason,
    }


def analyze(
    base: Register, plan: AmendmentPlan, documents: dict, cal=None, horizon: date | None = None
) -> dict:
    validate_evidence(base, plan, documents)
    after = candidate(base, plan)
    before_dates = {r.obligation.id: r for r in resolve(base, cal, horizon=horizon)}
    after_dates = {r.obligation.id: r for r in resolve(after, cal, horizon=horizon)}
    reasons = dependency_reasons(base, after, plan)
    blockers = [question.question for question in plan.questions]
    if plan.execution_status != "confirmed":
        blockers.append("Amendment execution status is not confirmed")
    if plan.effective_on is None or plan.effective_on > plan.as_of:
        blockers.append("Amendment is not established as effective on the review's as-of date")
    impacts = []
    for oid in sorted(reasons):
        old, new = before_dates.get(oid), after_dates.get(oid)
        impacted = bool(reasons[oid])
        if impacted and new and not new.resolved and not _waiting(after, oid):
            blockers.append(f"{oid}: {new.unresolved_reason or 'no calculable occurrence'}")
        if impacted and after.business_day_rule and after.business_day_rule.kind == "unresolved":
            rel = after.by_id(oid).trigger.relative if new else None
            if rel and rel.business_days:
                blockers.append(f"{oid}: Business Day definition remains unresolved")
        impacts.append(
            {
                "id": oid,
                "impacted": impacted,
                "reasons": sorted(reasons[oid]),
                "before": old.obligation.model_dump(mode="json") if old else None,
                "after": new.obligation.model_dump(mode="json") if new else None,
                "before_dates": _resolved(old),
                "after_dates": _resolved(new),
                "uid": f"{_slug(base.contract)}-{oid}@oblig-register",
                "action": "cancel"
                if new is None
                else "create"
                if old is None
                else "update"
                if impacted
                else "unchanged",
            }
        )
    return {
        "candidate": after.model_dump(mode="json"),
        "impacts": impacts,
        "blockers": sorted(set(blockers)),
        "as_of": plan.as_of.isoformat(),
        "synthetic": plan.synthetic,
        "limitations": [
            "Text-span checks establish provenance, not legal interpretation or completeness.",
            "Actor names are supplied attestations, not authenticated decision authority.",
            "Calendar exports do not update or remove events in an external calendar.",
        ],
    }
