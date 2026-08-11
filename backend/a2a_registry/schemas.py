from datetime import datetime
import re
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


Tier = Literal["standardized", "advanced"]
CardStatus = Literal["draft", "published", "suspended", "retired"]
ArtifactFormat = Literal["json", "uri", "json+uri"]
FailureBehavior = Literal["fail_fast", "retry_then_fallback", "dead_letter"]
AuthMethod = Literal["internal_api_key", "mtls", "oauth2"]


class HandoffRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_hops: int = Field(default=1, ge=1, le=8)
    require_human_approval: bool = False
    allowed_target_skills: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("allowed_target_skills")
    @classmethod
    def validate_target_skills(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("allowed_target_skills must be unique")
        for skill in values:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill):
                raise ValueError("allowed_target_skills must be lowercase slugs")
        return values


class CardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1.0", "1.1"] = "1.1"
    agent_id: str = Field(pattern=r"^agt-[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1)
    owner_team: str = Field(min_length=1, max_length=128)
    endpoint: HttpUrl
    skills: list[str] = Field(min_length=1, max_length=20)
    supported_tasks: list[str] = Field(min_length=1, max_length=20)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capability_tier: Tier
    discovery_only: bool
    message_task_format: str | None = None
    artifact_exchange: bool
    artifact_format: ArtifactFormat | None = None
    handoff_rules: HandoffRules = Field(default_factory=HandoffRules)
    timeout_seconds: int = Field(default=30, ge=1, le=900)
    failure_behavior: FailureBehavior = "fail_fast"
    authn_methods: list[AuthMethod] = Field(default_factory=lambda: ["internal_api_key"], min_length=1, max_length=3)
    authorized_callers: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("skills must be unique")
        for skill in values:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill):
                raise ValueError("skills must be lowercase slugs")
        return values

    @field_validator("supported_tasks")
    @classmethod
    def validate_tasks(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("supported_tasks must be unique")
        for task in values:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", task):
                raise ValueError("supported_tasks must be lowercase slugs")
        return values

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_schema_root(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object" or not value.get("properties"):
            raise ValueError("schema root must be an object with properties")
        return value

    @model_validator(mode="after")
    def validate_tier_exchange(self):
        if self.capability_tier == "standardized":
            if not self.discovery_only or self.message_task_format is not None or self.artifact_exchange or self.artifact_format is not None:
                raise ValueError("standardized cards must be discovery-only without exchange")
        elif self.discovery_only or not self.message_task_format or not self.artifact_exchange or self.artifact_format is None:
            raise ValueError("advanced cards require full exchange configuration and artifact format")
        if len(set(self.authn_methods)) != len(self.authn_methods):
            raise ValueError("authn_methods must be unique")
        return self


class CardUpdate(CardInput):
    expected_version: int = Field(ge=1)


class EligibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1.0"] = "1.0"
    source_agent_id: str = Field(pattern=r"^agt-[a-z0-9-]+$")
    a2a_enabled: bool
    capability_tier: Literal["minimal", "standardized", "advanced"]
    lifecycle_status: Literal["draft", "registered", "in_review", "approved", "live", "suspended", "retired"]
    registry_ready: bool
    runtime_ready: bool
    content_ready: bool
    source_version: str = Field(min_length=1, max_length=128)
    observed_at: datetime

    def is_eligible(self) -> bool:
        return self.a2a_enabled and self.capability_tier in {"standardized", "advanced"} and self.lifecycle_status == "live" and self.registry_ready and self.runtime_ready and self.content_ready


class HandoffValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_agent_id: str = Field(pattern=r"^agt-[a-z0-9-]+$")
    target_agent_id: str = Field(pattern=r"^agt-[a-z0-9-]+$")
    task: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    input_message: dict[str, Any]
    artifact_refs: list[str] = Field(default_factory=list, max_length=20)
    trace_correlation_id: str = Field(default_factory=lambda: f"trc-{uuid4()}", pattern=r"^trc-[0-9a-fA-F-]{36}$")
    approval_request_id: UUID | None = None


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)
