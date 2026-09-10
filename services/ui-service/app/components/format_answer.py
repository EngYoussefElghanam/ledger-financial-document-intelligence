"""Render schema-compliant answers and clickable PDF evidence citations."""

import html
import urllib.parse

PDF_VIEWER_URL = "/viewer/viewer.html"


def _esc(value) -> str:
    return html.escape(str(value))


def _pdf_link(document_id: str, page, quote: str | None = None) -> str | None:
    """Build a same-origin PDF.js viewer link for a grounded citation."""
    if not document_id or document_id == "unknown":
        return None
    safe_id = urllib.parse.quote(str(document_id), safe="")
    file_url = f"/api/documents/{safe_id}/pdf"
    url = f"{PDF_VIEWER_URL}?{urllib.parse.urlencode({'file': file_url})}"
    fragment = {}
    if page not in (None, "?"):
        fragment["page"] = str(page)
    if quote:
        fragment["search"] = " ".join(str(quote).split())
        fragment["phrase"] = "true"
    if fragment:
        url += f"#{urllib.parse.urlencode(fragment)}"
    return url


def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return '<div class="evidence-line">no evidence cited</div>'

    lines = []
    for item in evidence:
        document_id = item.get("document_id", "unknown")
        filename = item.get("filename")
        page = item.get("page", "?")
        section = item.get("section")
        quote = item.get("quote")

        label = f"{_esc(filename or document_id)} · p.{_esc(page)}"
        if section:
            label += f" · {_esc(section)}"

        link = _pdf_link(document_id, page, quote)
        if link:
            safe_link = html.escape(link, quote=True)
            content = f'<a href="{safe_link}" target="_blank" rel="noopener">{label} &#8599;</a>'
        else:
            content = label

        quote_html = (
            f'<div class="evidence-quote">&ldquo;{_esc(quote)}&rdquo;</div>'
            if quote else ""
        )
        lines.append(f'<div class="evidence-line">{content}{quote_html}</div>')
    return "\n".join(lines)


def format_answer(response: dict) -> str:
    """Return answer HTML ready for a Gradio chat bubble."""
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
        body = "<br>".join(f"— {_esc(value)}" for value in params.get("values", []))
    elif answer_type == "insufficient_evidence":
        reason = _esc(params.get("reason", "No reason given."))
        return f'<span class="ledger-flag">⚑ insufficient evidence</span><br>{reason}'
    else:
        return f'<span class="ledger-flag">⚑ unrecognized answer_type: {_esc(answer_type)}</span>'

    return f"{body}<hr style='margin:8px 0;border-color:#2A2E28'>{_format_evidence(evidence)}"
