"""Portable review page. All source content is escaped and no network is required."""

from __future__ import annotations

import html
import json
from importlib.resources import files


def esc(value):
    return html.escape(str(value))


def pretty(value):
    return esc(json.dumps(value, ensure_ascii=False, indent=2))


def comparison(value):
    if isinstance(value, dict):
        summary = value.get("verbatim") or value.get("description")
        if summary:
            return (
                f"<p>{esc(summary)}</p><details><summary>Full record</summary><pre>"
                + pretty(value)
                + "</pre></details>"
            )
        return "<pre>" + pretty(value) + "</pre>"
    return f'<p class="date">{esc(value) if value is not None else "None"}</p>'


def evidence(ref):
    return (
        f"<figure><blockquote>{esc(ref['quote'])}</blockquote><figcaption>"
        f"{esc(ref['document'])} · {esc(ref['locator'])} · "
        f"characters {ref['start']}–{ref['end']}</figcaption></figure>"
    )


def dates(row):
    if row is None:
        return "Not in this register"
    if row["deadline"]:
        return esc(row["deadline"])
    if row["occurrences"]:
        return (
            f"{len(row['occurrences'])} occurrences, "
            f"{esc(row['occurrences'][0])} to {esc(row['occurrences'][-1])}"
        )
    return esc(row["unresolved_reason"] or "No dated occurrence")


def render_review(package):
    body, digest = package["payload"], package["digest"]
    plan, analysis = body["plan"], body["analysis"]
    impacted = [r for r in analysis["impacts"] if r["impacted"]]
    blocks = analysis["blockers"]
    parts = [
        HEAD,
        f'<header><h1>Contract amendment review</h1><p class="title">{esc(plan["title"])}</p>',
        f"<p>As of {esc(plan['as_of'])} · {len(plan['changes'])} proposed changes · "
        f"{len(impacted)} affected obligations</p>",
    ]
    if plan["synthetic"]:
        parts.append(
            '<p class="notice">Synthetic example — documents and sign-offs are simulated.</p>'
        )
    parts.append("</header><main>")
    if blocks:
        parts.append(
            '<section class="blocked"><h2>Approval is blocked</h2><ul>'
            + "".join(f"<li>{esc(b)}</li>" for b in blocks)
            + "</ul><p>Resolve these questions in a new proposal and regenerate the review. "
            "You can record a rejection now.</p></section>"
        )
    else:
        parts.append(
            '<p class="notice">Ready for review. Publication still requires your decision on '
            "every change and acknowledgement of each affected obligation.</p>"
        )
    parts.append("<section><h2>Proposed changes</h2>")
    for change in plan["changes"]:
        parts.append(
            f"<article><h3>{esc(change['target'])}</h3><p>{esc(change['rationale'])}</p>"
            '<div class="compare"><div><h4>Current register</h4>'
            + comparison(change["before"])
            + "</div><div><h4>Proposed register</h4>"
            + comparison(change["after"])
            + "</div></div>"
        )
        parts.extend(evidence(ref) for ref in change["evidence"])
        parts.append(
            f'<label>Decision for {esc(change["id"])} <select data-change="{esc(change["id"])}">'
            '<option value="defer">Not decided</option><option value="accept">Accept</option>'
            '<option value="reject">Reject</option></select></label></article>'
        )
    if not plan["changes"]:
        parts.append("<p>No register changes proposed. Check the amendment coverage below.</p>")
    parts.append("</section><section><h2>Affected obligations</h2>")
    for row in impacted:
        item = row["after"] or row["before"]
        parts.append(
            f"<article><h3>{esc(item['description'])}</h3><p>{esc(item['obligor'])} → "
            f"{esc(item['obligee'])} · {esc(row['id'])} · {esc(row['action'])}</p>"
            '<div class="compare date"><div><h4>Before</h4>'
            + dates(row["before_dates"])
            + "</div><div><h4>After</h4>"
            + dates(row["after_dates"])
            + "</div></div><ul>"
            + "".join(f"<li>{esc(r)}</li>" for r in row["reasons"])
            + "</ul>"
        )
        parts.append(
            "<details><summary>Calculation traces and calendar action</summary><pre>"
            + pretty(
                {
                    "before": row["before_dates"],
                    "after": row["after_dates"],
                    "calendar_uid": row["uid"],
                    "action": row["action"],
                }
            )
            + "</pre></details>"
        )
        parts.append(
            f'<label class="check"><input type="checkbox" data-impact="{esc(row["id"])}"> '
            "I reviewed this impact, including any undated trigger or calendar action."
            "</label></article>"
        )
    if not impacted:
        parts.append(
            "<p>No mechanical obligation impacts identified. "
            "This does not establish legal completeness.</p>"
        )
    parts.append(
        "</section><section><h2>Amendment coverage</h2><p>Every non-whitespace character is "
        "accounted for. The reviewer remains responsible for the classification.</p>"
    )
    for section in plan["sections"]:
        parts.append(
            f"<details><summary>{esc(section['id'])} · "
            f"{esc(section['disposition'])}</summary>"
            f"<p>{esc(section['reason'])}</p>{evidence(section['evidence'])}</details>"
        )
    parts.append(
        "<details><summary>Original quotations, source hashes and calendar provenance"
        "</summary><pre>"
        + pretty(
            {
                "baseline": plan["baseline"],
                "baseline_notice": plan["baseline_notice"],
                "baseline_business_day_rule": plan["baseline_business_day_rule"],
                "inputs": body["inputs"],
                "calendar": body["calendar"],
                "effect_basis": plan["effect_basis"],
                "execution_status": plan["execution_status"],
                "effective_on": plan["effective_on"],
            }
        )
        + "</pre></details></section>"
    )
    parts.append(
        '<section class="decision"><h2>Record your decision</h2><p>Approval accepts the complete '
        "proposal. For partial acceptance, revise the proposal and generate a new review.</p>"
        '<form id="decision"><label>Your name and role'
        '<input id="actor" required autocomplete="name"></label>'
        '<label>Review evidence and basis<textarea id="basis" required minlength="8" rows="3" '
        'placeholder="Record what you reviewed and your authority to decide."></textarea></label>'
        '<div class="actions"><button id="approve" type="submit" value="approved">'
        "Download approval</button>"
        '<button class="secondary" type="submit" value="rejected">Download rejection</button></div>'
        '<p id="status" role="status">Downloaded decisions must be validated '
        "with obligreg amend apply.</p>"
        "</form><ul>"
        + "".join(f"<li>{esc(t)}</li>" for t in analysis["limitations"])
        + "</ul><details><summary>Review fingerprint</summary><code>"
        + digest
        + "</code></details></section></main></body>"
    )
    data = json.dumps(
        {"digest": digest, "blocked": bool(blocks), "synthetic": plan["synthetic"]}
    ).replace("<", "\\u003c")
    parts.append("<script>const review=" + data + ";" + SCRIPT + "</script></html>")
    return "".join(parts)


HEAD = files("obligreg").joinpath("assets/review-head.html").read_text(encoding="utf-8")
SCRIPT = files("obligreg").joinpath("assets/review.js").read_text(encoding="utf-8")
