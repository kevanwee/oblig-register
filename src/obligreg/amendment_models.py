"""Strict, separate schemas for source-backed proposals and review decisions."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .models import NoticeClause, NoticeMethod, Obligation, Recurrence, Relative, Trigger

SHA = r"^[a-f0-9]{64}$"
ID = r"^[a-z][a-z0-9-]{0,62}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    id: str = Field(pattern=ID)
    role: Literal["agreement", "amendment"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA)


class Evidence(Strict):
    document: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    locator: str = Field(min_length=1)


class StrictRelative(Relative):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=0, ge=0)
    business_days: int = Field(default=0, ge=0)
    months: int = Field(default=0, ge=0)


class StrictRecurrence(Recurrence):
    model_config = ConfigDict(extra="forbid")


class StrictTrigger(Trigger):
    model_config = ConfigDict(extra="forbid")
    relative: StrictRelative | None = None
    recurrence: StrictRecurrence | None = None

    @model_validator(mode="after")
    def _single_shape(self):
        fields = {
            "fixed": "date",
            "relative": "relative",
            "event": "event",
            "recurring": "recurrence",
        }
        if any(
            getattr(self, key) is not None for key in fields.values() if key != fields[self.kind]
        ):
            raise ValueError("trigger includes fields belonging to another trigger kind")
        return self


class ProposedObligation(Obligation):
    model_config = ConfigDict(extra="forbid")
    trigger: StrictTrigger


class ProposedNoticeMethod(NoticeMethod):
    model_config = ConfigDict(extra="forbid")


class ProposedNotice(NoticeClause):
    model_config = ConfigDict(extra="forbid")
    methods: list[ProposedNoticeMethod] = Field(default_factory=list)


class Change(Strict):
    id: str = Field(pattern=ID)
    kind: Literal["replace", "add", "remove", "field"]
    target: str
    before: Any
    after: Any
    rationale: str = Field(min_length=8)
    evidence: list[Evidence] = Field(min_length=1)


class Section(Strict):
    id: str = Field(pattern=ID)
    evidence: Evidence
    disposition: Literal["change", "unaffected", "question"]
    changes: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=8)


class Question(Strict):
    id: str = Field(pattern=ID)
    question: str = Field(min_length=8)
    evidence: list[Evidence] = Field(min_length=1)


class AmendmentPlan(Strict):
    schema_version: Literal["1"] = "1"
    title: str = Field(min_length=5)
    as_of: date
    effective_on: date | None
    execution_status: Literal["confirmed", "unconfirmed"]
    effect_basis: str = Field(min_length=8)
    sources: list[Source] = Field(min_length=2)
    baseline: dict[str, Evidence]
    baseline_notice: Evidence | None = None
    baseline_business_day_rule: Evidence | None = None
    sections: list[Section] = Field(min_length=1)
    changes: list[Change]
    questions: list[Question] = Field(default_factory=list)
    synthetic: bool = False

    @model_validator(mode="after")
    def _identities(self):
        for rows in (self.sources, self.sections, self.changes, self.questions):
            ids = [item.id for item in rows]
            if len(set(ids)) != len(ids):
                raise ValueError("duplicate source, section, change or question id")
        if {s.role for s in self.sources} != {"agreement", "amendment"}:
            raise ValueError("provide both agreement and amendment sources")
        targets = [(change.kind == "field", change.target) for change in self.changes]
        if len(set(targets)) != len(targets):
            raise ValueError("combine changes to the same field/obligation into one proposal")
        return self


class Decision(Strict):
    schema_version: Literal["1"] = "1"
    package_digest: str = Field(pattern=SHA)
    outcome: Literal["approved", "rejected"]
    actor: str = Field(min_length=1, pattern=r"\S")
    evidence: str = Field(min_length=8, pattern=r"\S")
    reviewed_at: AwareDatetime
    changes: dict[str, Literal["accept", "reject", "defer"]]
    impacts_acknowledged: list[str]
    synthetic: bool = False
