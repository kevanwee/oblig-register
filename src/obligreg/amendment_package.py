"""Immutable review packages and fail-closed publication of approved registers."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

import yaml

from .amendment_models import AmendmentPlan, Decision
from .amendments import analyze, canonical, sha, sources
from .calendars import FrozenCalendar
from .ics import to_ics
from .models import Register, load_register
from .resolve import resolve

ENGINE = "oblig-register/amendment-1"


def inputs(base_path: Path, plan_path: Path):
    base = load_register(base_path)
    plan = AmendmentPlan.model_validate_json(plan_path.read_bytes())
    documents = sources(plan, plan_path.parent)
    hashes = {
        "base": sha(base_path.read_bytes()),
        "plan": sha(plan_path.read_bytes()),
        "sources": {key: row["sha256"] for key, row in documents.items()},
    }
    return base, plan, documents, hashes


def payload(base, plan, documents, hashes, calendar=None, horizon=None):
    normalized = plan.model_dump(mode="json")
    for source in normalized["sources"]:
        source["path"] = f"sources/{source['id']}.txt"
    analysis = analyze(
        base, plan, documents, FrozenCalendar(calendar) if calendar else None, horizon=horizon
    )
    return {
        "engine": ENGINE,
        "inputs": hashes,
        "base": base.model_dump(mode="json"),
        "plan": normalized,
        "calendar": calendar,
        "horizon": horizon.isoformat() if horizon else None,
        "analysis": analysis,
    }


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _publish(output, writer):
    """Only our own staging directory is cleaned on failure. Never overwrite output."""
    output = Path(output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / f".{output.name}.publish.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        if output.exists():
            raise ValueError("Output already exists; use a new review/version directory")
        with tempfile.TemporaryDirectory(prefix=".obligreg-", dir=output.parent) as staging:
            stage = Path(staging) / "content"
            stage.mkdir()
            writer(stage)
            if output.exists():
                raise ValueError("Output appeared during publication")
            stage.rename(output)
    finally:
        lock.unlink()


def build(base_path: Path, plan_path: Path, output: Path, *, calendar=None, horizon=None):
    from .amendment_ui import render_review

    base, plan, documents, hashes = inputs(base_path, plan_path)
    body = payload(base, plan, documents, hashes, calendar, horizon)
    package = {"digest": sha(canonical(body)), "payload": body}

    def write(stage):
        _json(stage / "review.json", package)
        (stage / "base.yaml").write_bytes(base_path.read_bytes())
        (stage / "proposal.json").write_bytes(plan_path.read_bytes())
        (stage / "sources").mkdir()
        for key, document in documents.items():
            (stage / "sources" / f"{key}.txt").write_bytes(document["raw"])
        (stage / "review.html").write_bytes(render_review(package).encode("utf-8"))

    _publish(output, write)
    return package


def verify(directory: Path, base_path: Path, plan_path: Path):
    from .amendment_ui import render_review

    package = json.loads((directory / "review.json").read_bytes())
    body = package["payload"]
    if body["engine"] != ENGINE or sha(canonical(body)) != package["digest"]:
        raise ValueError("Review package changed or has an unsupported engine version")
    base, plan, documents, hashes = inputs(base_path, plan_path)
    if hashes != body["inputs"]:
        raise ValueError("Current inputs changed; build and approve a new review")
    if (
        sha((directory / "base.yaml").read_bytes()) != hashes["base"]
        or sha((directory / "proposal.json").read_bytes()) != hashes["plan"]
    ):
        raise ValueError("Frozen input files changed")
    for key, document in documents.items():
        if (directory / "sources" / f"{key}.txt").read_bytes() != document["raw"]:
            raise ValueError("Frozen source changed")
    horizon = date.fromisoformat(body["horizon"]) if body["horizon"] else None
    expected = payload(base, plan, documents, hashes, body["calendar"], horizon)
    if canonical(expected) != canonical(body):
        raise ValueError("Recomputed impacts differ from the reviewed package")
    if (directory / "review.html").read_bytes() != render_review(package).encode():
        raise ValueError("Review presentation changed; regenerate the review")
    return package


def apply(directory: Path, base_path: Path, plan_path: Path, decision_path: Path, output: Path):
    package = verify(directory, base_path, plan_path)
    body, digest = package["payload"], package["digest"]
    decision = Decision.model_validate_json(decision_path.read_bytes())
    if decision.package_digest != digest:
        raise ValueError("Decision belongs to a different review package")
    if decision.synthetic != body["plan"]["synthetic"]:
        raise ValueError("Synthetic status must match the review")
    expected_changes = {row["id"] for row in body["plan"]["changes"]}
    if set(decision.changes) != expected_changes:
        raise ValueError("Decision must account for exactly every proposed change")
    analysis = body["analysis"]
    if decision.outcome == "approved":
        if analysis["blockers"] or any(v != "accept" for v in decision.changes.values()):
            raise ValueError("Approval requires no blockers and acceptance of every change")
        expected_impacts = {r["id"] for r in analysis["impacts"] if r["impacted"]}
        if set(decision.impacts_acknowledged) != expected_impacts or len(
            decision.impacts_acknowledged
        ) != len(expected_impacts):
            raise ValueError("Acknowledge exactly every affected obligation")

    def write(stage):
        _json(stage / "decision.json", decision.model_dump(mode="json"))
        _json(
            stage / "receipt.json",
            {
                "package_digest": digest,
                "outcome": decision.outcome,
                "synthetic": decision.synthetic,
                "authority": "supplied attestation; not authenticated",
                "input_hashes": body["inputs"],
                "calendar": body["calendar"],
            },
        )
        if decision.outcome == "rejected":
            return
        reg = Register.model_validate(analysis["candidate"])
        calendar = FrozenCalendar(body["calendar"]) if body["calendar"] else None
        horizon = date.fromisoformat(body["horizon"]) if body["horizon"] else None
        resolved = resolve(reg, calendar, horizon=horizon)
        (stage / "register.yaml").write_text(
            yaml.safe_dump(reg.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
        (stage / "calendar.ics").write_text(to_ics(resolved, reg), encoding="utf-8", newline="")
        _json(
            stage / "calendar-changes.json",
            {
                "status": "proposed external calendar actions; no calendar was changed",
                "actions": [r for r in analysis["impacts"] if r["impacted"]],
            },
        )
        _json(stage / "resolution.json", analysis)

    _publish(output, write)
    return decision.outcome
