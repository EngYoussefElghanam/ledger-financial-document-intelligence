"""
Renders a schema-compliant answer dict (answer_type/evidence/params) as
HTML for the Gradio chat window, styled to match the ledger identity —
evidence entries as ledger line items, figures as tabular monospace.
"""

import html


def _esc(value) -> str:
    """HTML-escape any interpolated value. Financial data routinely
    contains characters like & (AT&T, R&D) or < that would otherwise
    corrupt the rendered HTML."""
    return html.escape(str(value))


def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return '<div class="evidence-line">no evidence cited</div>'

    lines = []
    for ev in evidence:
        doc = _esc(ev.get("document_id", "unknown"))
        page = _esc(ev.get("page", "?"))
        section = ev.get("section")
        text = f"{doc} \u00b7 p.{page}"
        if section:
            text += f" \u00b7 {_esc(section)}"
        lines.append(f'<div class="evidence-line">{text}</div>')
    return "\n".join(lines)


def format_answer(response: dict) -> str:
    """
    response: the dict returned by client.ask_question()
    Returns an HTML string ready to drop into a Gradio chat bubble.
    """
    answer_type = response.get("answer_type")
    params = response.get("params", {})
    evidence = response.get("evidence", [])

    if answer_type == "direct":
        body = f'<span class="ledger-value">{_esc(params.get("value"))}</span>'

    elif answer_type == "calculated":
        value = _esc(params.get("value"))
        formula = _esc(params.get("formula", ""))
        body = (
            f'<span class="ledger-value">{value}</span>'
            f'<br><span class="evidence-line">formula: {formula}</span>'
        )

    elif answer_type == "multi_span":
        values = params.get("values", [])
        body = "<br>".join(f"\u2014 {_esc(v)}" for v in values)

    elif answer_type == "insufficient_evidence":
        reason = _esc(params.get("reason", "No reason given."))
        return f'<span class="ledger-flag">\u2691 insufficient evidence</span><br>{reason}'

    else:
        return f'<span class="ledger-flag">\u2691 unrecognized answer_type: {_esc(answer_type)}</span>'

    return f"{body}<hr style='margin:8px 0;border-color:#2A2E28'>{_format_evidence(evidence)}"
