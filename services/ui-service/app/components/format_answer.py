"""
Renders a schema-compliant answer dict (answer_type/evidence/params) as
HTML for the Gradio chat window, styled to match the ledger identity —
evidence entries as ledger line items, figures as tabular monospace.
"""

import html
import os
import urllib.parse

# Bonus feature: when set, evidence citations link directly to the source
# PDF page. Left empty, evidence renders as plain text — same behavior
# as before this was added, no crash either way.
PDF_BASE_URL = os.getenv("PDF_BASE_URL", "").rstrip("/")


def _esc(value) -> str:
    """HTML-escape any interpolated value. Financial data routinely
    contains characters like & (AT&T, R&D) or < that would otherwise
    corrupt the rendered HTML."""
    return html.escape(str(value))


def _pdf_link(document_id: str, page) -> str | None:
    """Builds a link to the source PDF at the cited page, if PDF_BASE_URL
    is configured. Returns None (no link) if it isn't, or if document_id/
    page aren't usable — callers must handle the None case."""
    if not PDF_BASE_URL:
        return None
    if not document_id or document_id == "unknown":
        return None
    safe_id = urllib.parse.quote(str(document_id))
    url = f"{PDF_BASE_URL}/{safe_id}.pdf"
    if page not in (None, "?"):
        url += f"#page={urllib.parse.quote(str(page))}"
    return url


def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return '<div class="evidence-line">no evidence cited</div>'

    lines = []
    for ev in evidence:
        doc_id = ev.get("document_id", "unknown")
        page = ev.get("page", "?")
        section = ev.get("section")
        doc = _esc(doc_id)
        page_esc = _esc(page)
        text = f"{doc} \u00b7 p.{page_esc}"
        if section:
            text += f" \u00b7 {_esc(section)}"

        link = _pdf_link(doc_id, page)
        if link:
            # Escape the URL for the HTML attribute too — document_id/page
            # are already escaped above; the URL itself is built from the
            # same values via urllib.parse.quote, but escape defensively.
            safe_link = html.escape(link, quote=True)
            content = f'<a href="{safe_link}" target="_blank" rel="noopener">{text} &#8599;</a>'
        else:
            content = text

        lines.append(f'<div class="evidence-line">{content}</div>')
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
