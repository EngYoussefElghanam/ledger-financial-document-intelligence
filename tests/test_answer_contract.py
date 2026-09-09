"""Run with python -m unittest discover -s tests -p test_answer_contract.py."""

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location(
    "validator_main", ROOT / "services/answer-validator-api/app/main.py"
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class AnswerContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(validator.app)

    def validate(self, kind, params, evidence=None):
        return self.client.post("/validate_answer", json={
            "answer_type": kind,
            "params": params,
            "evidence": evidence if evidence is not None else [
                {"document_id": "report", "page": 1}
            ],
        }).json()

    def test_all_answer_types(self):
        cases = [
            ("direct", {"value": "$42M"}),
            ("calculated", {"value": 2.5, "formula": "5/2"}),
            ("multi_span", {"values": ["Revenue", "Expenses"]}),
            ("insufficient_evidence", {"reason": "No indexed documents"}),
        ]
        for kind, params in cases:
            with self.subTest(kind=kind):
                self.assertTrue(self.validate(kind, params)["valid"])

    def test_citations_required_for_factual_answers(self):
        self.assertFalse(self.validate("direct", {"value": 42}, [])["valid"])
        self.assertTrue(self.validate(
            "insufficient_evidence", {"reason": "No documents"}, []
        )["valid"])

    def test_bad_calculation_and_page_rejected(self):
        self.assertFalse(self.validate("calculated", {"value": 42})["valid"])
        self.assertFalse(self.validate("direct", {"value": 42}, [
            {"document_id": "report", "page": 0}
        ])["valid"])


if __name__ == "__main__":
    unittest.main()
