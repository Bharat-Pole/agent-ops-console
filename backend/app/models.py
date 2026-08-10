"""Increment A data model — users/RBAC, agent control records, intent
drafts vs immutable documents, polymorphic approvals, append-only audit.

Doctrine encoded here (from the approved master plan):
- Governed objects: create → version → supersede → retain. DELETE exists only
  for drafts.
- Drafts are strictly separated from immutable submissions.
- Audit actor is ALWAYS server-derived (a user id), never client-supplied.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, JsonDoc


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- identity & RBAC (9 Blueprint roles) -----------------------------------

class Role(str, enum.Enum):
    business_user = "business_user"
    agent_creator = "agent_creator"
    agent_owner = "agent_owner"
    ai_engineer = "ai_engineer"
    governance_reviewer = "governance_reviewer"
    evaluator = "evaluator"
    platform_admin = "platform_admin"
    finops_admin = "finops_admin"
    security_data_owner = "security_data_owner"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    roles: Mapped[list["RoleAssignment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="RoleAssignment.user_id",  # granted_by is a second FK to users
    )

    def role_set(self) -> set[Role]:
        return {ra.role for ra in self.roles}


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=40))
    # dual-control provenance for platform_admin grants (Pass 10)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship(back_populates="roles", foreign_keys=[user_id])


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


# ---- agent registry ---------------------------------------------------------

class LifecycleStatus(str, enum.Enum):
    draft = "draft"
    sandbox = "sandbox"
    candidate = "candidate"
    approved_prototype = "approved_prototype"
    production_candidate = "production_candidate"
    production = "production"
    needs_review = "needs_review"
    deprecated = "deprecated"
    retired = "retired"


class RiskTier(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    restricted = "restricted"


class AgentControlRecord(Base):
    """The hub record — nearly everything links back to agent_id."""
    __tablename__ = "agent_control_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    intent_type: Mapped[str] = mapped_column(String(40), default="new_agent")  # | existing_agent_onboarding
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        Enum(LifecycleStatus, native_enum=False, length=40), default=LifecycleStatus.draft, index=True
    )
    business_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    technical_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    governance_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(120), nullable=True)
    draft_risk_tier: Mapped[RiskTier | None] = mapped_column(Enum(RiskTier, native_enum=False, length=20), nullable=True)
    confirmed_risk_tier: Mapped[RiskTier | None] = mapped_column(Enum(RiskTier, native_enum=False, length=20), nullable=True)
    current_intent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    current_intent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    design_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    row_version: Mapped[int] = mapped_column(Integer, default=1)


class AgentIntentDraft(Base):
    """Mutable auto-save state. The ONLY governed-adjacent object with DELETE."""
    __tablename__ = "agent_intent_drafts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_control_records.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # 6 field groups
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IntentStatus(str, enum.Enum):
    submitted = "submitted"
    recommendation_ready = "recommendation_ready"
    recommendation_failed = "recommendation_failed"
    superseded = "superseded"


class AgentIntentDocument(Base):
    """Immutable once written. New submission = new version row; prior rows get
    status=superseded (field update only — payload is never touched)."""
    __tablename__ = "agent_intent_documents"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[IntentStatus] = mapped_column(
        Enum(IntentStatus, native_enum=False, length=40), default=IntentStatus.submitted
    )
    payload: Mapped[dict] = mapped_column(JsonDoc)          # frozen 6 field groups (Prov-enveloped leaves)
    pii_flags: Mapped[list] = mapped_column(JsonDoc, default=list)
    validation: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # warnings + rules_version at submit
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class DesignRecommendation(Base):
    """One generation run over one immutable intent version. Regeneration
    creates a new row (create→version doctrine); the control record points at
    the current one."""
    __tablename__ = "design_recommendations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_intent_documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="ready")   # ready | failed
    engine: Mapped[str] = mapped_column(String(40), default="")        # deterministic | llm+deterministic
    raw_output: Mapped[dict] = mapped_column(JsonDoc, default=dict)    # LLM raw + deterministic trace
    items: Mapped[list] = mapped_column(JsonDoc, default=list)         # normalized review items
    validation: Mapped[dict] = mapped_column(JsonDoc, default=dict)    # basis overlap verdicts, closed-world results, contradictions
    item_states: Mapped[dict] = mapped_column(JsonDoc, default=dict)   # per-item accept/reject
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---- governance primitives --------------------------------------------------

class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Approval(Base):
    """Polymorphic approval record. actor_user_id is written from the session
    at decision time — never accepted from the client (verified-finding fix)."""
    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)   # agent|prompt|tool|workflow|deployment|exception|...
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    step: Mapped[str] = mapped_column(String(80))                        # e.g. governance_review, security_signoff
    required_role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=40))
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=20), default=ApprovalStatus.pending, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---- Increment C: Asset Studio ---------------------------------------------

class SecretRecord(Base):
    """Vault entry. Values encrypted at rest (app key, Fernet); the API NEVER
    returns values — names only (carried /v1/tools/try lesson)."""
    __tablename__ = "secrets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ModelCatalogEntry(Base):
    __tablename__ = "model_catalog"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40))            # gemini | anthropic | ...
    model_ref: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)    # llm | embedding | judge
    display_name: Mapped[str] = mapped_column(String(120))
    cost_per_1k_in: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_1k_out: Mapped[float] = mapped_column(Float, default=0.0)
    latency_note: Mapped[str] = mapped_column(String(120), default="")
    max_risk_tier: Mapped[str] = mapped_column(String(20), default="high")  # highest tier allowed to use it
    status: Mapped[str] = mapped_column(String(20), default="active")       # active | disabled
    fallback_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Vault secret NAME holding this model's API key — same contract as tools.
    # Lets keys rotate without a restart and lets different teams/agents run on
    # different credentials. Falls back to the bootstrap env var when unset.
    credential_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PermissionType(str, enum.Enum):
    read = "read"
    summarize = "summarize"
    draft = "draft"
    recommend = "recommend"
    validate = "validate"
    create = "create"
    update = "update"
    approve = "approve"
    deploy = "deploy"


WRITE_PERMISSION_TYPES = {PermissionType.create, PermissionType.update,
                          PermissionType.approve, PermissionType.deploy}


class AssetStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    deprecated = "deprecated"


class ToolRecord(Base):
    """Tool Registry (Pass 3 — the 'how tools are defined' answer). Declared
    implementation binding only — name-magic is banned platform-wide."""
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("slug", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    business_purpose: Mapped[str] = mapped_column(Text, default="")
    permission_type: Mapped[PermissionType] = mapped_column(
        Enum(PermissionType, native_enum=False, length=20), default=PermissionType.read
    )
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    input_schema: Mapped[dict] = mapped_column(JsonDoc, default=dict)   # full JSON Schema
    output_schema: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    # {kind: http_api | mcp | builtin:web_search | none, config: {...}}
    implementation: Mapped[dict] = mapped_column(JsonDoc, default=lambda: {"kind": "none", "config": {}})
    # {method: none | api_key_header | bearer, credential_ref: secret name (names only)}
    auth: Mapped[dict] = mapped_column(JsonDoc, default=lambda: {"method": "none", "credential_ref": None})
    rate_limit_per_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    logging_requirement: Mapped[str] = mapped_column(String(40), default="standard")
    human_approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    error_handling: Mapped[dict] = mapped_column(JsonDoc, default=lambda: {"retry_count": 0, "fallback_behavior": "fail_gracefully"})
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, native_enum=False, length=30), default=AssetStatus.draft, index=True
    )
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | mcp_discovery | materialized
    mcp_connector_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class McpConnector(Base):
    __tablename__ = "mcp_connectors"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    endpoint: Mapped[str] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(String(20), default="streamable_http")  # streamable_http | sse
    auth: Mapped[dict] = mapped_column(JsonDoc, default=lambda: {"header_name": None, "credential_ref": None})
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | disabled
    health: Mapped[dict] = mapped_column(JsonDoc, default=lambda: {"ok": None, "last_checked": None, "consecutive_failures": 0})
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PromptPack(Base):
    __tablename__ = "prompt_packs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    prompt_type: Mapped[str] = mapped_column(String(40), default="system")  # 10 Blueprint types
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JsonDoc, default=list)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromptVersion(Base):
    """Immutable content. Rollback = NEW version pointing at prior content."""
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("pack_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prompt_packs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    variables: Mapped[list] = mapped_column(JsonDoc, default=list)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, native_enum=False, length=30), default=AssetStatus.draft
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    rolled_back_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(80), default="text/plain")
    sensitivity: Mapped[str] = mapped_column(String(20), default="internal")
    access_policy: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    validity_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")  # uploaded|ingesting|ready|failed|disabled
    file_path: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedded: Mapped[bool] = mapped_column(Boolean, default=False)  # False → keyword-only retrieval (labeled)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KbChunk(Base):
    """Chunking is ACTUALLY applied (carried lesson). Embedding column is
    pgvector on Postgres; JSON float list on SQLite (vector adapter seam)."""
    __tablename__ = "kb_chunks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    ord: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # {location: "page 3" | "chars 0-800"}
    embedding: Mapped[list | None] = mapped_column(JsonDoc, nullable=True)  # adapter reads/writes; see adapters/vectors.py


class RagPipeline(Base):
    __tablename__ = "rag_pipelines"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    source_ids: Mapped[list] = mapped_column(JsonDoc, default=list)
    chunk_size: Mapped[int] = mapped_column(Integer, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=120)
    embedding_model_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    score_threshold: Mapped[float] = mapped_column(Float, default=0.25)  # ENFORCED at retrieval
    hybrid_alpha: Mapped[float] = mapped_column(Float, default=0.7)      # vector weight in hybrid blend
    metadata_filters: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssetBinding(Base):
    """Agent↔asset reference: fresh-resolve via version_policy (Decision 1.1);
    deployment snapshots pin exact versions (Increment F)."""
    __tablename__ = "asset_bindings"
    __table_args__ = (UniqueConstraint("agent_id", "asset_type", "asset_ref"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(20))  # tool | prompt | knowledge | rag | model
    asset_ref: Mapped[str] = mapped_column(String(140))  # slug or model_ref (stable across versions)
    version_policy: Mapped[str] = mapped_column(String(40), default="latest_approved")  # latest_approved | pinned
    pinned_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---- Increment D: workflows + execution ------------------------------------

class WorkflowStatus(str, enum.Enum):
    draft = "draft"
    validated = "validated"
    pending_approval = "pending_approval"
    approved = "approved"
    active = "active"
    rejected = "rejected"
    superseded = "superseded"


class Workflow(Base):
    __tablename__ = "workflows"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowVersion(Base):
    """Immutable once past draft. What runs is EXACTLY what was approved —
    editing an active version forks a new draft (fork-on-edit)."""
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # {nodes:[{id,type,label,config}], edges:[{from,to,when?}]}
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, native_enum=False, length=30), default=WorkflowStatus.draft, index=True
    )
    validation: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # violations/warnings/adjustments at validate time
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RunStatus(str, enum.Enum):
    running = "running"
    paused_hitl = "paused_hitl"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowRun(Base):
    """One execution. The single telemetry source (Pass 8): dashboards and
    evaluation read runs + steps — there is no second pipeline."""
    __tablename__ = "workflow_runs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_versions.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="interactive")  # interactive | evaluation | deployed
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=20), default=RunStatus.running, index=True
    )
    input: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    output: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class RunStep(Base):
    """Per-node span: the real trace. Telemetry, cost, and evaluation all read
    from here (concern #2: nothing fabricated)."""
    __tablename__ = "run_steps"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    ord: Mapped[int] = mapped_column(Integer)
    node_id: Mapped[str] = mapped_column(String(80))
    node_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | failed | refused | paused
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # policy decisions, citation check, previews
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunHitl(Base):
    """Durable human-approval gate inside a run: the run checkpoint pauses at
    the node; deciding here RESUMES it. Actor server-derived, as everywhere."""
    __tablename__ = "run_hitl"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    node_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending | approved | denied
    payload: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # what is being approved (state summary)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---- Increment E: governance config + evaluation ----------------------------

class PolicyConfigRow(Base):
    """Versioned governance configuration (approval matrix, eval gates,
    staleness). Changes create a NEW version; decisions record which version
    applied."""
    __tablename__ = "policy_configs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    config: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalPack(Base):
    __tablename__ = "eval_packs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    threshold: Mapped[float] = mapped_column(Float, default=70.0)  # scorecard pass mark (0-100)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalCase(Base):
    __tablename__ = "eval_cases"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_packs.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(30), default="golden")  # golden|boundary|refusal|no_write|data_boundary|tool_call|regression|latency|cost|safety
    input: Mapped[str] = mapped_column(Text)
    expectations: Mapped[dict] = mapped_column(JsonDoc, default=dict)  # expectations DSL
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | llm_generated
    review_status: Mapped[str] = mapped_column(String(20), default="reviewed")  # llm_generated start pending
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalRun(Base):
    """One pack execution against one workflow version. The scorecard is
    computed ONLY from real workflow runs (mode=evaluation)."""
    __tablename__ = "eval_runs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_packs.id"), index=True)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|completed|failed
    scorecard: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_cases.id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = not evaluable (recorded why)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    checks: Mapped[list] = mapped_column(JsonDoc, default=list)  # [{check, ok, note}]


class EvidencePack(Base):
    """Frozen promotion evidence: scorecard snapshot, version refs, approvals,
    sample trace ids — assembled at promote time, immutable after."""
    __tablename__ = "evidence_packs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    content: Mapped[dict] = mapped_column(JsonDoc, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GovernanceException(Base):
    """Logged exception register (Pass 4): expiry hard-capped at 180 days;
    only lets Low/Medium agents through a failed eval gate — never High/Restricted."""
    __tablename__ = "governance_exceptions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | expired | revoked
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---- Increment F: deployment + access + FinOps ------------------------------

class AccessGroup(Base):
    __tablename__ = "access_groups"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    """Hashed at rest (sha256); plaintext returned exactly once at creation."""
    __tablename__ = "api_keys"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("access_groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(12))  # display only
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deployment(Base):
    """Immutable manifest (Decision 1.1: deploy-time snapshot): what runs on
    the channel is EXACTLY this frozen graph + pinned assets — fresh-resolve
    stops at the deployment boundary. Rollback re-activates a prior manifest
    as a NEW record."""
    __tablename__ = "deployments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), index=True)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_versions.id"))
    slug: Mapped[str] = mapped_column(String(80), index=True)  # invoke path; agent slug + channel
    channel: Mapped[str] = mapped_column(String(20), default="sandbox")  # sandbox | production (Decision 7.3)
    manifest: Mapped[dict] = mapped_column(JsonDoc, default=dict)        # FROZEN graph + asset pins
    admission: Mapped[dict] = mapped_column(JsonDoc, default=dict)       # check results at deploy time
    access_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("access_groups.id"), nullable=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | superseded | rolled_back
    previous_deployment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_control_records.id"), unique=True)
    monthly_usd: Mapped[float] = mapped_column(Float)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedbackRecord(Base):
    __tablename__ = "feedback_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # -1 | +1
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Append-only. No update/delete code paths exist for this table; the actor
    is the authenticated session user. (Hash-chaining: recorded deferral.)"""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(255))                # denormalized display (email + roles at time)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[dict] = mapped_column(JsonDoc, default=dict)
