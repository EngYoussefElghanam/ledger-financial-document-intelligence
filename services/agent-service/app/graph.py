import re
import json

from typing import TypedDict, Literal, Optional
from dotenv import load_dotenv

load_dotenv("../../.env")

from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

from app.tools import calculate, search_documents, search_tables, filter_documents
from app.telemetry import record_llm
from app.config import AGENT_MODEL
from ledger_observability import observation

llm = ChatGroq(model=AGENT_MODEL, temperature=0)


def invoke_llm(stage: str, prompt: str):
    with observation(
        stage,
        as_type="generation",
        input=prompt,
        model=AGENT_MODEL,
    ) as span:
        response = llm.invoke(prompt)
        record_llm(stage, response)
        span.update(
            output=extract_text(response.content),
            usage_details=getattr(response, "usage_metadata", None),
        )
        return response


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
    """Extract plain text from model responses, handling string and block lists."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [block.get("text", "") for block in content if isinstance(block, dict)]
        return " ".join(texts)
    return str(content)


def classify_question(state: AgentState) -> dict:
    """Classifies question phrasing into: numerical, table, or text."""
    prompt = f"""Classify this financial question into exactly one category, based on how the question is PHRASED, not on where the answer might typically be found in a document:
- "numerical": explicitly requires a calculation (sum, difference, percentage change, comparison between values)
- "table": explicitly references tabular structure — rows, columns, a specific line item compared across multiple periods, or comparing several structured values at once
- "text": a general factual question, even one about a financial figure like revenue or profit, as long as it does not explicitly reference tabular structure

Most simple "what was X" or "what is X" questions about a single figure are "text", not "table" — a single fact is often stated in narrative form even in a table-heavy document.

Question: {state['question']}

Reply with ONLY one word: numerical, table, or text."""

    response = invoke_llm("classify_question", prompt)
    category = extract_text(response.content).strip().lower()

    if category not in ["numerical", "table", "text"]:
        category = "text"

    return {"question_type": category, "retries": 0, "calculation": None}


def retrieve_evidence(state: AgentState) -> dict:
    """Retrieves relevant chunks, dynamically expanding search scope on retries."""
    question = state["question"]
    doc_id = state.get("document_id")
    q_lower = question.lower()
    retries = state.get("retries", 0)

    # Dynamic limit: expand search space on retry (5 -> 10 -> 15)
    fetch_limit = 5 + (retries * 5)

    # Check if question explicitly targets a known financial section (Metadata filtering)
    known_sections = [
        "income statement", 
        "balance sheet", 
        "cash flows", 
        "operating expenses", 
        "financial highlights"
    ]
    matched_section = next((sec for sec in known_sections if sec in q_lower), None)

    # 1. Use filter_documents if a specific section and document_id are targeted (first attempt only)
    if matched_section and doc_id and retries == 0:
        c_type = "table" if state["question_type"] == "table" else None
        results = filter_documents.invoke({
            "document_id": doc_id,
            "section": matched_section,
            "content_type": c_type
        })
        if results and "error" not in results[0]:
            return {"evidence": results[:fetch_limit]}

    # 2. On retry, if table search failed, fallback to general search to explore surrounding narrative text
    q_type = state["question_type"]
    if q_type == "table" and retries > 0:
        q_type = "text"

    # 3. Retrieve chunks with expanded limit
    if q_type == "table":
        results = search_tables.invoke({"query": question, "document_id": doc_id, "limit": fetch_limit})
    else:
        results = search_documents.invoke({"query": question, "document_id": doc_id, "limit": fetch_limit})

    return {"evidence": results}


def check_evidence_sufficiency(state: AgentState) -> dict:
    """Verifies whether retrieved evidence contains sufficient context to answer."""
    evidence = state["evidence"]

    if not evidence or (evidence and "error" in evidence[0]):
        return {"is_sufficient": False}

    evidence_text = "\n".join([
        f"- {e.get('text', '')}" for e in evidence
    ])

    q_type = state.get("question_type", "text")

    entity_guidance = (
        "(Note: The evidence is extracted directly from the target company's financial filing, "
        "so references to 'the Company' or general tabular line items correspond to the entity in question.)"
    )

    # For numerical questions, check if required numbers for calculation exist
    if q_type == "numerical":
        prompt = f"""{evidence_text}

Does this evidence contain the financial figures or numbers needed to calculate or answer the question "{state['question']}"?
{entity_guidance}

Reply with ONLY one word: yes or no."""
    else:
        prompt = f"""{evidence_text}

Does this evidence contain the answer to the question "{state['question']}"?
{entity_guidance}

Reply with ONLY one word: yes or no."""

    response = invoke_llm("check_evidence_sufficiency", prompt)
    answer = extract_text(response.content).strip().lower()

    return {"is_sufficient": "yes" in answer}


def route_after_evidence_check(state: AgentState) -> str:
    """Conditional routing based on evidence sufficiency and question category."""
    if state["is_sufficient"]:
        if state["question_type"] == "numerical":
            return "extract_and_calculate"
        return "generate_answer"
    elif state["retries"] < 2:
        return "increment_retry"
    else:
        return "insufficient_evidence"


def extract_and_calculate(state: AgentState) -> dict:
    """Extracts arithmetic operands and formula, then executes deterministic calculation tool."""
    question = state["question"]
    evidence = state["evidence"]

    evidence_text = "\n".join([
        f"- [{idx}] {e.get('text', '')} (document: {e.get('metadata', {}).get('document_id')}, "
        f"page: {e.get('metadata', {}).get('page_number')}, section: {e.get('metadata', {}).get('section')})"
        for idx, e in enumerate(evidence)
    ])

    extraction_prompt = f"""You are extracting numeric operands from evidence to build an arithmetic expression.
Do NOT calculate the result yourself. Only extract the numbers and the operation needed.

Rules:
- Do NOT use the '%' symbol. Express percentages as decimals or division (e.g. use '/100' or '0.05', never '5%').
- You must ONLY use numbers explicitly found in the evidence chunks above.
- You must specify the exact evidence chunk index for every operand.

Question: {question}

Evidence:
{evidence_text}

Reply with ONLY a JSON object, no markdown, no extra text:
{{
  "formula": "<a valid arithmetic expression using ONLY numbers found in the evidence, e.g. '(3875-3410)/3410*100'>",
  "operand_evidence_indices": [<list of 0-based indices into the evidence list above that were used as operands>],
  "scale": "" | "thousand" | "million" | "billion" | "percent"
}}

If the evidence does not contain the numbers needed to answer, reply with:
{{"formula": null, "operand_evidence_indices": []}}
"""

    response = invoke_llm("extract_operands", extraction_prompt)
    raw = extract_text(response.content).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        extraction = json.loads(raw)
    except json.JSONDecodeError:
        extraction = {"formula": None, "operand_evidence_indices": []}

    formula = extraction.get("formula")
    used_indices = extraction.get("operand_evidence_indices", [])
    scale = str(extraction.get("scale") or "").lower()

    if not formula:
        return {"calculation": None}

    # Fix 3: Removed '%' from allowed characters to prevent modulo confusion in numexpr
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\)\s]+", formula):
        return {"calculation": None}

    # Fix 1: Strictly require valid operand citations - never fake citations with evidence[0]
    if (
        not used_indices
        or not isinstance(used_indices, list)
        or any(type(index) is not int or index < 0 or index >= len(evidence) for index in used_indices)
    ):
        return {"calculation": None}
    if scale not in {"", "thousand", "million", "billion", "percent"}:
        return {"calculation": None}

    # Execute deterministic calculation tool via Python
    tool_result = calculate.invoke({"expression": formula})

    if not isinstance(tool_result, dict) or not tool_result.get("success"):
        return {"calculation": None}

    calc_value = tool_result.get("result")

    operand_evidence = [
        {
            "document_id": evidence[i].get("metadata", {}).get("document_id"),
            "page": evidence[i].get("metadata", {}).get("page_number"),
            "section": evidence[i].get("metadata", {}).get("section"),
        }
        for i in used_indices
    ]

    # If any cited index was out of range or empty, reject rather than fabricate
    if not operand_evidence:
        return {"calculation": None}

    return {
        "calculation": {
            "value": calc_value,
            "formula": formula,
            "scale": scale,
            "evidence": operand_evidence,
        }
    }



def route_after_calculation(state: AgentState) -> str:
    """Conditional routing: route to generate_answer if calculation succeeded, else insufficient_evidence."""
    if state.get("calculation"):
        return "generate_answer"
    return "insufficient_evidence"


def generate_answer(state: AgentState) -> dict:
    """Generates strict schema-compliant response grounded in retrieved evidence."""
    question = state["question"]
    evidence = state["evidence"]
    q_type = state["question_type"]
    calculation = state.get("calculation")

    # For numerical questions, return deterministic calculation result
    if calculation:
        return {
            "answer": {
                "answer_type": "calculated",
                "evidence": calculation["evidence"],
                "params": {
                    "value": calculation["value"],
                    "formula": calculation["formula"],
                    "scale": calculation.get("scale", ""),
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
  "evidence": [{{"document_id": "...", "page": 1, "section": "..."}}],
  "params": {{}}
}}

Rules:
- "direct": single fact, params = {{"value": ..., "scale": "" | "thousand" | "million" | "billion" | "percent"}}
- "multi_span": params = {{"values": [...], "scale": "" | "thousand" | "million" | "billion" | "percent"}}
"""

    response = invoke_llm("generate_answer", prompt)
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
    """Returns fallback insufficient_evidence answer when context is missing."""
    return {
        "answer": {
            "answer_type": "insufficient_evidence",
            "evidence": [],
            "params": {"reason": "No sufficient evidence found or calculation could not be performed"}
        }
    }


def increment_retry(state: AgentState) -> dict:
    """Increments retry counter for conditional looping."""
    return {"retries": state["retries"] + 1}


def build_graph():
    """Constructs and compiles the StateGraph reasoning pipeline."""
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

    # Conditional routing based on evidence sufficiency
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

    # Conditional routing after calculation
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
