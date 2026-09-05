def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return '<div class="evidence-line">no evidence cited</div>'

    lines = []
    for ev in evidence:
        doc = ev.get("document_id", "unknown")
        page = ev.get("page", "?")
        section = ev.get("section")
        text = f"{doc} \u00b7 p.{page}"
        if section:
            text += f" \u00b7 {section}"
        lines.append(f'<div class="evidence-line">{text}</div>')
    return "\n".join(lines)


def format_answer(response: dict) -> str:
 
    answer_type = response.get("answer_type")
    params = response.get("params", {})
    evidence = response.get("evidence", [])

    if answer_type == "direct":
        body = f'<span class="ledger-value">{params.get("value")}</span>'

    elif answer_type == "calculated":
        value = params.get("value")
        formula = params.get("formula", "")
        body = (
            f'<span class="ledger-value">{value}</span>'
            f'<br><span class="evidence-line">formula: {formula}</span>'
        )

    elif answer_type == "multi_span":
        values = params.get("values", [])
        body = "<br>".join(f"\u2014 {v}" for v in values)

    elif answer_type == "insufficient_evidence":
        reason = params.get("reason", "No reason given.")
        return f'<span class="ledger-flag">\u2691 insufficient evidence</span><br>{reason}'

    else:
        return f'<span class="ledger-flag">\u2691 unrecognized answer_type: {answer_type}</span>'

    return f"{body}<hr style='margin:8px 0;border-color:#D9D3C7'>{_format_evidence(evidence)}"
