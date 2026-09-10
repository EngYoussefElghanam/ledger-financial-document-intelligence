from app.answer_adapter import answer_to_prediction
from app.metrics.answer import score_answer


def score(gold, prediction, *, gold_scale="", pred_scale="", answer_type="span"):
    return score_answer(
        gold_answer=gold,
        gold_scale=gold_scale,
        gold_answer_type=answer_type,
        is_answerable=True,
        predicted_answer=prediction,
        predicted_scale=pred_scale,
    )


def test_exact_match_normalizes_commas_and_scale():
    result = score("304,811", 304811, gold_scale="thousand", pred_scale="thousand")
    assert result["em"] == 1
    assert result["f1"] == 1


def test_numerical_accuracy_handles_percent_equivalence():
    result = score(
        23.42,
        0.2342,
        gold_scale="percent",
        pred_scale="",
        answer_type="arithmetic",
    )
    assert result["numerical_accuracy"] == 1


def test_multi_span_alignment_is_order_independent():
    result = score(["2019", "2020"], ["2020", "2019"], answer_type="multi-span")
    assert result["em"] == 1
    assert result["f1"] == 1


def test_partial_multi_span_gets_partial_f1():
    result = score(["trade debtors", "prepayments"], ["trade debtors"], answer_type="multi-span")
    assert result["em"] == 0
    assert 0 < result["f1"] < 1


def test_unanswerable_requires_refusal():
    result = score_answer(
        gold_answer=None,
        gold_scale="",
        gold_answer_type="unanswerable",
        is_answerable=False,
        predicted_answer=None,
        predicted_scale="",
    )
    assert result == {"em": 1.0, "f1": 1.0, "numerical_accuracy": None}


def test_answer_adapter_preserves_explicit_scale():
    value, scale = answer_to_prediction(
        {
            "answer_type": "calculated",
            "evidence": [{"document_id": "d", "page": 1}],
            "params": {"value": 4.6, "formula": "46/10", "scale": "percent"},
        }
    )
    assert value == 4.6
    assert scale == "percent"

