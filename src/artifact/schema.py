"""
Artifact Schema — the core data model.

A CapabilityArtifact is saved after discovery and loaded for replay.
It is the contract between:
  - the LLM agent     (writes it)
  - the replay engine (reads it)
  - the calling agent (invokes it with typed inputs, gets typed outputs)
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class LocatorStrategy(BaseModel):
    """
    How to find a UI element during replay.
    We store primary + fallbacks so replay degrades gracefully
    if a selector breaks (e.g. an ID changes on the legacy app).
    Preference order: name attribute > label text > visible text > XPath
    """
    primary: str
    fallbacks: List[str] = []
    description: str          # human-readable, for reviewability


class ActionStep(BaseModel):
    """One recorded action in the flow."""
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: Literal["navigate", "click", "type", "read", "assert", "wait"]
    locator: Optional[LocatorStrategy] = None

    # Value stored as TEMPLATE (e.g. "{{member_id}}"), not resolved value.
    # This is what makes the artifact reusable across invocations.
    value: Optional[str] = None

    # CSS selector that must exist after this step — verifies it worked
    checkpoint: Optional[str] = None

    # safe=read-only/reversible  risky=changes state  irreversible=cannot undo
    risk: Literal["safe", "risky", "irreversible"] = "safe"

    # What replay does if this step fails
    on_error: Literal["fail", "retry", "escalate"] = "fail"

    description: str = ""     # the LLM's reason for choosing this action


class InputParam(BaseModel):
    """A parameter the calling agent supplies per invocation (e.g. member_id)."""
    name: str
    type: Literal["string", "integer", "boolean"]
    description: str
    required: bool = True


class OutputField(BaseModel):
    """A value the replay engine extracts and returns to the caller."""
    key: str                    # e.g. "savings_balance"
    locator: LocatorStrategy
    extraction: Literal["text", "value", "attribute"] = "text"
    redact: bool = False        # True = never log this (PII / sensitive)


class SuccessCondition(BaseModel):
    """
    The condition replay checks at the end to confirm the goal was met.
    Different from per-step checkpoints — this is the overall goal assertion.
    """
    type: Literal["url_contains", "element_exists", "text_present"]
    value: str


class CapabilityArtifact(BaseModel):
    """
    A saved, reusable, versioned automation capability.
    Produced by: discovery agent
    Consumed by: replay executor
    Reviewed by: human operators
    """
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "1.0"
    name: str
    description: str
    target_url: str
    surface_type: Literal["web", "legacy_web", "desktop"] = "legacy_web"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["draft", "approved"] = "draft"

    # The public contract (what the caller provides and gets back)
    input_params: Dict[str, InputParam] = {}
    output_schema: Dict[str, OutputField] = {}

    # The recorded flow
    steps: List[ActionStep]
    success_condition: SuccessCondition


class ReplayResult(BaseModel):
    """
    Three distinct outcome categories — by design, not by convention.

    success          → goal reached, outputs populated
    business_outcome → known expected non-success (e.g. "member not found")
                       NOT a bug — the caller handles this
    hard_failure     → something went wrong, needs investigation
    """
    status: Literal["success", "business_outcome", "hard_failure"]
    outputs: Dict[str, str] = {}
    business_outcome: Optional[str] = None   # e.g. "member_not_found"
    failed_step_id: Optional[str] = None
    error_detail: Optional[str] = None
    screenshot_path: Optional[str] = None