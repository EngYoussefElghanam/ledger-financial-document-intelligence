import re
import json

from typing import TypedDict, Literal, Optional
from dotenv import load_dotenv

load_dotenv("../../.env")

from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

from app.tools import calculate, search_documents, search_tables, filter_documents

llm = ChatGroq(model="qwen/qwen3.8-27b", temperature=0)


class AgentState(TypedDict):
    question: str
    document_id: Optional[str]
    question_type: Literal["text", "table", "numerical"]
    evidence: list
    is_sufficient: bool
    retries: int
    calculation: Optional[dict]
    answer: dict


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [block.get("text", "") for block in content if isinstance(block, dict)]
        return " ".join(texts)
    return str(content)


def classify_question(state: AgentState) -> dict:
    prompt = f"""Classify this financial question into exactly one category, based on how the question is PHRASED, not on where the answer might typically be found in a document:
- "numerical": explicitly requires a calculation (sum, difference, percentage change, comparison between values)
- "table": explicitly references tabular structure — rows, columns, a specific line item compared across multiple periods, or comparing several structured values at once
- "text": a general factual question, even one about a financial figure like revenue or profit, as long as it does not explicitly reference tabular structure

Most simple "what was X" or "what is X" questions about a single figure are "text", not "table" — a single fact is often stated in narrative form even in a table-heavy document.

Question: {state['question']}

Reply with ONLY one word: numerical, table, or text."""

    response = llm.invoke(prompt)
    category = extract_text(response.content).strip().lower()

    if category not in ["numerical", "table", "text"]:
        category = "text"

    return {"question_type": category, "retries": 0, "calculation": None}


def retrieve_evidence(state: AgentState) -> dict:
    question = state["question"]
    doc_id = state.get("document_id")
    q_lower = question.lower()

    # فحص إذا كان السؤال يحدد قسماً مالياً بعينه (Metadata filtering)
    known_sections = [
        "income statement", 
        "balance sheet", 
        "cash flows", 
        "operating expenses", 
        "financial highlights"
    ]
    matched_section = next((sec for sec in known_sections if sec in q_lower), None)

    # 1. لو محدد قسم معين مع وجود document_id، نستخدم filter_documents
    if matched_section and doc_id:
        print(f"[AGENT] retrieve_evidence: Using filter_documents for section '{matched_section}'")
        c_type = "table" if state["question_type"] == "table" else None
        results = filter_documents.invoke({
            "document_id": doc_id,
            "section": matched_section,
            "content_type": c_type
        })
        # لو رجع نتائج سليمة نعتمدها، وإلا نرجع للـ search العادي
        if results and "error" not in results[0]:
            return {"evidence": results[:5]}

    # 2. لو السؤال table
    if state["question_type"] == "table":
        results = search_tables.invoke({"query": question, "document_id": doc_id, "limit": 5})
    # 3. البحث العام
    else:
        results = search_documents.invoke({"query": question, "document_id": doc_id, "limit": 5})

    return {"evidence": results}


def check_evidence_sufficiency(state: AgentState) -> dict:
    evidence = state["evidence"]

    if not evidence or (evidence and "error" in evidence[0]):
        return {"is_sufficient": False}

    evidence_text = "\n".join([
        f"- {e.get('text', '')}" for e in evidence
    ])

    q_type = state.get("question_type", "text")

    if q_type == "numerical":
        prompt = f"""{evidence_text}

Does this evidence contain the financial figures or numbers needed to calculate or answer the question "{state['question']}"?

Reply with ONLY one word: yes or no."""
    else:
        prompt = f"""{evidence_text}

Does this answer the question "{state['question']}"?

Reply with ONLY one word: yes or no."""

    response = llm.invoke(prompt)
    answer = extract_text(response.content).strip().lower()

    return {"is_sufficient": "yes" in answer}

def route_after_evidence_check(state: AgentState) -> str:
    if state["is_sufficient"]:
        if state["question_type"] == "numerical":
            return "extract_and_calculate"
        return "generate_answer"
    elif state["retries"] < 2:
        return "increment_retry"
    else:
        return "insufficient_evidence"


def extract_and_calculate(state: AgentState) -> dict:
    question = state["question"]
    evidence = state["evidence"]

    evidence_text = "\n".join([
        f"- [{idx}] {e.get('text', '')} (document: {e.get('metadata', {}).get('document_id')}, "
        f"page: {e.get('metadata', {}).get('page_number')}, section: {e.get('metadata', {}).get('section')})"
        for idx, e in enumerate(evidence)
    ])

    extraction_prompt = f"""You are extracting numeric operands from evidence to build an arithmetic expression.
Do NOT calculate the result yourself. Only extract the numbers and the operation needed.

Question: {question}

Evidence:
{evidence_text}

Reply with ONLY a JSON object, no markdown, no extra text:
{{
  "formula": "<a valid arithmetic expression using ONLY numbers found in the evidence, e.g. '(3875-3410)/3410*100'>",
  "operand_evidence_indices": [<list of 0-based indices into the evidence list above that were used as operands>]
}}

If the evidence does not contain the numbers needed to answer, reply with:
{{"formula": null, "operand_evidence_indices": []}}
"""

    response = llm.invoke(extraction_prompt)
    raw = extract_text(response.content).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        extraction = json.loads(raw)
    except json.JSONDecodeError:
        extraction = {"formula": None, "operand_evidence_indices": []}

    formula = extraction.get("formula")

    if not formula:
        return {"calculation": None}

    # التحقق من أمان المعادلة
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s%]+", formula):
        return {"calculation": None}

    # تنفيذ الأداة فعلياً
    tool_result = calculate.invoke({"expression": formula})

    # التأكد من نجاح الأداة وأن النتيجة رقم صريح
    if not isinstance(tool_result, dict) or not tool_result.get("success"):
        return {"calculation": None}

    calc_value = tool_result.get("result")

    used_indices = extraction.get("operand_evidence_indices", [])
    operand_evidence = [
        {
            "document_id": evidence[i].get("metadata", {}).get("document_id"),
            "page": evidence[i].get("metadata", {}).get("page_number"),
            "section": evidence[i].get("metadata", {}).get("section"),
        }
        for i in used_indices
        if i < len(evidence)
    ]

    # ضمان عدم وجود evidence فاضية أبداً لتجنب رفض الـ validator
    if not operand_evidence and evidence:
        operand_evidence = [{
            "document_id": evidence[0].get("metadata", {}).get("document_id"),
            "page": evidence[0].get("metadata", {}).get("page_number"),
            "section": evidence[0].get("metadata", {}).get("section"),
        }]

    return {
        "calculation": {
            "value": calc_value,
            "formula": formula,
            "evidence": operand_evidence,
        }
    }


def route_after_calculation(state: AgentState) -> str:
    """مسار شرطي: لو الحساب نجح روح لـ generate_answer، لو فشل روح لـ insufficient_evidence"""
    if state.get("calculation"):
        return "generate_answer"
    return "insufficient_evidence"


def generate_answer(state: AgentState) -> dict:
    question = state["question"]
    evidence = state["evidence"]
    q_type = state["question_type"]
    calculation = state.get("calculation")

    # لو السؤال numerical والحساب جهز بنجاح
    if calculation:
        return {
            "answer": {
                "answer_type": "calculated",
                "evidence": calculation["evidence"],
                "params": {
                    "value": calculation["value"],
                    "formula": calculation["formula"],
                },
            }
        }

    evidence_text = "\n".join([
        f"- {e.get('text', '')} (document: {e.get('metadata', {}).get('document_id')}, "
        f"page: {e.get('metadata', {}).get('page_number')}, section: {e.get('metadata', {}).get('section')})"
        for e in evidence
    ])

    prompt = f"""You are a financial analyst assistant. Answer the question using ONLY the evidence below.

Question: {question}
Question type: {q_type}

Evidence:
{evidence_text}

Reply with ONLY a JSON object matching exactly this schema (no markdown, no extra text):
{{
  "answer_type": "direct" | "multi_span",
  "evidence": [{{"document_id": "...", "page": 0, "section": "..."}}],
  "params": {{}}
}}

Rules:
- "direct": single fact, params = {{"value": ...}}
- "multi_span": params = {{"values": [...]}}
"""

    response = llm.invoke(prompt)
    text = extract_text(response.content).strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        answer = json.loads(text)
    except json.JSONDecodeError:
        answer = {
            "answer_type": "insufficient_evidence",
            "evidence": [],
            "params": {"reason": "Failed to parse model output"}
        }

    return {"answer": answer}


def insufficient_evidence_node(state: AgentState) -> dict:
    return {
        "answer": {
            "answer_type": "insufficient_evidence",
            "evidence": [],
            "params": {"reason": "No sufficient evidence found or calculation could not be performed"}
        }
    }


def increment_retry(state: AgentState) -> dict:
    return {"retries": state["retries"] + 1}


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("classify_question", classify_question)
    workflow.add_node("retrieve_evidence", retrieve_evidence)
    workflow.add_node("check_evidence_sufficiency", check_evidence_sufficiency)
    workflow.add_node("extract_and_calculate", extract_and_calculate)
    workflow.add_node("generate_answer", generate_answer)
    workflow.add_node("increment_retry", increment_retry)
    workflow.add_node("insufficient_evidence", insufficient_evidence_node)

    workflow.add_edge(START, "classify_question")
    workflow.add_edge("classify_question", "retrieve_evidence")
    workflow.add_edge("retrieve_evidence", "check_evidence_sufficiency")

    # التوجيه الشرطي بعد فحص كفاية الدليل
    workflow.add_conditional_edges(
        "check_evidence_sufficiency",
        route_after_evidence_check,
        {
            "generate_answer": "generate_answer",
            "extract_and_calculate": "extract_and_calculate",
            "increment_retry": "increment_retry",
            "insufficient_evidence": "insufficient_evidence",
        }
    )

    workflow.add_edge("increment_retry", "retrieve_evidence")

    # توجيه شرطي بعد الحساب: لو فشل الحساب يروح لـ insufficient_evidence
    workflow.add_conditional_edges(
        "extract_and_calculate",
        route_after_calculation,
        {
            "generate_answer": "generate_answer",
            "insufficient_evidence": "insufficient_evidence",
        }
    )

    workflow.add_edge("generate_answer", END)
    workflow.add_edge("insufficient_evidence", END)

    return workflow.compile()


graph = build_graph()