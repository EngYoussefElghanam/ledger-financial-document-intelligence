"""
This is the answer contract, the strict schema both agent-service(producer) and answer-validator-api(consumer) depend on.

Design: a discriminated union on `answer_type`. Each concrete answer type
gets its own `params` model with exactly the fields the spec requires —
this is what lets us reject e.g. a 'calculated' answer missing 'formula'
with a specific error instead of a generic "invalid schema" message.
"""

from typing import Literal, Union
from pydantic import BaseModel, Field, field_validator


class Evidence(BaseModel):
    document_id: str
    page: int
    section: str | None = None  # optional per the spec's examples


# One params model per answer_type 

class DirectParams(BaseModel):
    value: str | int | float


class CalculatedParams(BaseModel):
    value: int | float
    formula: str


class MultiSpanParams(BaseModel):
    values: list[str | int | float]

    @field_validator("values")
    @classmethod
    def must_have_at_least_two(cls, v):
        # Spec: multi_span means "two or more distinct values" — a single
        # value should have been sent as `direct` instead.
        if len(v) < 2:
            raise ValueError("multi_span requires at least 2 values")
        return v


class InsufficientEvidenceParams(BaseModel):
    reason: str


# One full answer model per type, each pinning its own params type

class DirectAnswer(BaseModel):
    answer_type: Literal["direct"]
    evidence: list[Evidence] = Field(..., min_length=1)
    params: DirectParams


class CalculatedAnswer(BaseModel):
    answer_type: Literal["calculated"]
    evidence: list[Evidence] = Field(..., min_length=1)
    params: CalculatedParams


class MultiSpanAnswer(BaseModel):
    answer_type: Literal["multi_span"]
    evidence: list[Evidence] = Field(..., min_length=1)
    params: MultiSpanParams


class InsufficientEvidenceAnswer(BaseModel):
    answer_type: Literal["insufficient_evidence"]
    evidence: list[Evidence] = Field(default_factory=list)  # allowed empty
    params: InsufficientEvidenceParams


# The discriminated union: this is what you'll import elsewhere 

Answer = Union[
    DirectAnswer,
    CalculatedAnswer,
    MultiSpanAnswer,
    InsufficientEvidenceAnswer,
]