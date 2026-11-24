from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class EmailSender(BaseModel):
    name: str = ""
    email: str


class EmailPayload(BaseModel):
    id: str
    received_at: str
    from_: EmailSender = Field(alias="from")
    to: str = "support@kesarandco.example"
    subject: str = ""
    body: str = ""
    attachments: list[str] = Field(default_factory=list)

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True


class ClassificationResult(BaseModel):
    intent: Literal["order_status", "product_query", "return_refund", "complaint", "other"]
    secondary_intent: Literal["order_status", "product_query", "return_refund", "complaint", "other"] | None = None
    order_id: str | None = None
    sentiment: Literal["positive", "neutral", "negative", "angry"]
    language: Literal["en", "hi", "hinglish"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(max_length=200)
    prompt_injection_detected: bool = False


class ToolTrace(BaseModel):
    tool: str
    args: dict[str, Any]
    result_summary: str


class PipelineResult(BaseModel):
    email_id: str
    classification: ClassificationResult
    order_found: bool
    privacy_blocked: bool = False
    action_taken: str
    needs_human: bool
    ticket_id: str | None = None
    reply_draft: str
    prompt_version: str
    processed_at: str
    tools_used: list[ToolTrace] = Field(default_factory=list)
    tokens_est: int = 0
    cost_inr_est: float = 0.0
    error: str = ""
    notes: str = ""


def to_dict(obj: BaseModel) -> dict[str, Any]:
    return obj.model_dump() if hasattr(obj, "model_dump") else obj.dict()
