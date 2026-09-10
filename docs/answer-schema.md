# Answer contract

Every public answer uses the discriminated union defined in
`shared/schemas/answer.py`. Unknown fields are rejected. Pages are one-based,
and every answer other than `insufficient_evidence` must cite at least one
document and page.

## Direct answer

```json
{
  "answer_type": "direct",
  "evidence": [{"document_id": "report-2025", "page": 7, "section": "Revenue"}],
  "params": {"value": 142.5, "scale": "million"}
}
```

## Calculated answer

```json
{
  "answer_type": "calculated",
  "evidence": [{"document_id": "report-2025", "page": 9, "section": "Expenses"}],
  "params": {"value": 13.64, "formula": "(500-440)/440*100", "scale": "percent"}
}
```

The formula must use values grounded in the cited evidence. Arithmetic is
executed by the deterministic calculation tool rather than by the language
model.

## Multi-span answer

```json
{
  "answer_type": "multi_span",
  "evidence": [
    {"document_id": "report-2024", "page": 4},
    {"document_id": "report-2025", "page": 4}
  ],
  "params": {"values": [120, 142.5], "scale": "million"}
}
```

`values` must contain at least two entries.

## Insufficient evidence

```json
{
  "answer_type": "insufficient_evidence",
  "evidence": [],
  "params": {"reason": "The indexed filings do not contain the requested figure."}
}
```

Supported scales are `""`, `"thousand"`, `"million"`, `"billion"`, and
`"percent"`. The validator endpoint is `POST /validate_answer` on port 8004;
the orchestrator validates agent output before returning it.
