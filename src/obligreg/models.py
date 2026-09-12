"""Register schema. `schema/register.schema.json` is generated from this file."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class Category(StrEnum):
    PAYMENT = "payment"
    DELIVERY = "delivery"
    NOTICE = "notice"
    REPORTING = "reporting"
    RENEWAL = "renewal"
    TERMINATION = "termination"
    INSURANCE = "insurance"
    COMPLIANCE = "compliance"
    CONFIDENTIALITY = "confidentiality"
    DATA = "data"
    IP = "ip"
    OTHER = "other"


class Freq(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class Relative(BaseModel):
    """'within 30 days after X' / 'not less than 60 days before Y'."""

    anchor: str = Field(
        description="'effective_date' | 'expiry' | an obligation id | 'event:<name>'"
    )
    days: int = 0
    business_days: int = 0
    months: int = 0
    direction: str = Field(default="after", pattern="^(after|before)$")

    @model_validator(mode="after")
    def _one_unit(self) -> Relative:
        if sum(1 for v in (self.days, self.business_days, self.months) if v) != 1:
            raise ValueError("relative trigger needs exactly one of days / business_days / months")
        return self


class Recurrence(BaseModel):
    freq: Freq
    start: dt.date | None = Field(default=None, description="defaults to effective_date")
    until: dt.date | None = Field(default=None, description="defaults to expiry")
    day_of_month: int | None = Field(default=None, ge=1, le=28)


class Trigger(BaseModel):
    kind: str = Field(pattern="^(fixed|relative|event|recurring)$")
    date: dt.date | None = None
    relative: Relative | None = None
    event: str | None = Field(default=None, description="plain description of the event")
    recurrence: Recurrence | None = None

    @model_validator(mode="after")
    def _shape(self) -> Trigger:
        need = {"fixed": "date", "relative": "relative", "event": "event",
                "recurring": "recurrence"}[self.kind]
        if getattr(self, need) is None:
            raise ValueError(f"trigger kind {self.kind!r} requires `{need}`")
        return self


class Obligation(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    obligor: str
    obligee: str
    category: Category = Category.OTHER
    description: str = Field(min_length=8)
    clause_ref: str
    verbatim: str = Field(min_length=15, description="the operative words, quoted exactly")
    trigger: Trigger
    condition: str | None = Field(default=None, description="only if ...")
    consequence: str | None = Field(default=None, description="what happens on breach/lapse")
    lead_days: int = Field(default=14, ge=0, description="reminder lead time for the calendar")
    notes: list[str] = Field(default_factory=list)


class NoticeMethod(BaseModel):
    """Parameters for sg-deadline's deemed_receipt tool, lifted from the notice clause."""

    method: str
    offset_days: int = 0
    business_days: bool = False
    cutoff: dt.time | None = None
    non_working_day_defers: bool = False
    roll_to_working_day: bool = False


class NoticeClause(BaseModel):
    clause_ref: str
    verbatim: str = Field(min_length=15)
    addresses: dict[str, str] = Field(default_factory=dict, description="party -> address")
    methods: list[NoticeMethod] = Field(default_factory=list)


class Register(BaseModel):
    contract: str
    parties: list[str] = Field(min_length=2)
    effective_date: dt.date | None = None
    expiry: dt.date | None = None
    governing_law: str | None = None
    events: dict[str, dt.date] = Field(
        default_factory=dict, description="known dates for event triggers, e.g. termination"
    )
    notice_clause: NoticeClause | None = None
    obligations: list[Obligation]

    @field_validator("events", mode="before")
    @classmethod
    def _none_is_empty(cls, v):
        # A YAML `events:` key holding only comments parses as None; treat it as {}.
        return {} if v is None else v

    @model_validator(mode="after")
    def _refs(self) -> Register:
        ids = [o.id for o in self.obligations]
        if len(ids) != len(set(ids)):
            dup = next(i for i in ids if ids.count(i) > 1)
            raise ValueError(f"duplicate obligation id {dup!r}")
        for o in self.obligations:
            if o.obligor not in self.parties:
                raise ValueError(f"{o.id}: obligor {o.obligor!r} is not a party")
            rel = o.trigger.relative
            if rel and rel.anchor not in ("effective_date", "expiry") \
                    and not rel.anchor.startswith("event:") and rel.anchor not in ids:
                raise ValueError(f"{o.id}: relative anchor {rel.anchor!r} is not an obligation id")
        return self

    def by_id(self, oid: str) -> Obligation:
        for o in self.obligations:
            if o.id == oid:
                return o
        raise KeyError(oid)


def load_register(path: str | Path) -> Register:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Register.model_validate(raw)


def json_schema() -> dict:
    return Register.model_json_schema()
