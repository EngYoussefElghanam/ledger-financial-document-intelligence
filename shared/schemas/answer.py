"""Typed answer contract shared by the agent and answer validator."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(ContractModel):
    document_id: str = Field(min_length=1)
    page: int = Field(ge=1, strict=True)
    section: str | None = None
    filename: str | None = None
    quote: str | None = None


Value = Union[StrictStr, StrictInt, StrictFloat]
Scale = Literal["", "thousand", "million", "billion", "percent"]


class DirectParams(ContractModel):
    value: Value
    scale: Scale = ""


class CalculatedParams(ContractModel):
    value: Union[StrictInt, StrictFloat]
    formula: str = Field(min_length=1)
    scale: Scale = ""


class MultiSpanParams(ContractModel):
    values: list[Value] = Field(min_length=2)
    scale: Scale = ""


class InsufficientEvidenceParams(ContractModel):
    reason: str = Field(min_length=1)


class DirectAnswer(ContractModel):
    answer_type: Literal["direct"]
    evidence: list[Evidence] = Field(min_length=1)
    params: DirectParams


class CalculatedAnswer(ContractModel):
    answer_type: Literal["calculated"]
    evidence: list[Evidence] = Field(min_length=1)
    params: CalculatedParams


class MultiSpanAnswer(ContractModel):
    answer_type: Literal["multi_span"]
    evidence: list[Evidence] = Field(min_length=1)
    params: MultiSpanParams


class InsufficientEvidenceAnswer(ContractModel):
    answer_type: Literal["insufficient_evidence"]
    evidence: list[Evidence]
    params: InsufficientEvidenceParams


Answer = Annotated[
    Union[DirectAnswer, CalculatedAnswer, MultiSpanAnswer, InsufficientEvidenceAnswer],
    Field(discriminator="answer_type"),
]
