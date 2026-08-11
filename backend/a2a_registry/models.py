import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class AgentCard(Base):
    __tablename__ = "agent_cards"
    __table_args__ = (
        CheckConstraint("capability_tier IN ('standardized', 'advanced')", name="ck_a2a_tier"),
        CheckConstraint("card_status IN ('draft', 'published', 'suspended', 'retired')", name="ck_a2a_status"),
        CheckConstraint(
            "(capability_tier = 'standardized' AND discovery_only AND message_task_format IS NULL AND NOT artifact_exchange) "
            "OR (capability_tier = 'advanced' AND NOT discovery_only AND message_task_format IS NOT NULL AND artifact_exchange)",
            name="ck_a2a_tier_exchange",
        ),
        {"schema": "a2a"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    contract_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.1")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_team: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    supported_tasks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    capability_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    discovery_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    message_task_format: Mapped[str | None] = mapped_column(String(128))
    artifact_exchange: Mapped[bool] = mapped_column(Boolean, nullable=False)
    artifact_format: Mapped[str | None] = mapped_column(String(32))
    handoff_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    failure_behavior: Mapped[str] = mapped_column(String(32), nullable=False, default="fail_fast")
    authn_methods: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    authorized_callers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    card_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    card_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = (UniqueConstraint("agent_card_id", "skill", name="uq_a2a_card_skill"), {"schema": "a2a"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("a2a.agent_cards.id", ondelete="CASCADE"), nullable=False)
    skill: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EligibilityAttestation(Base):
    __tablename__ = "eligibility_attestations"
    __table_args__ = ({"schema": "a2a"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    a2a_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    capability_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    registry_ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    runtime_ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content_ready: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)


class AgentCardVersion(Base):
    __tablename__ = "agent_card_versions"
    __table_args__ = (UniqueConstraint("agent_card_id", "card_version", name="uq_a2a_card_version"), {"schema": "a2a"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("a2a.agent_cards.id", ondelete="RESTRICT"), nullable=False, index=True)
    card_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = ({"schema": "a2a"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    card_version: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HandoffApprovalRequest(Base):
    __tablename__ = "handoff_approval_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_a2a_approval_status"),
        {"schema": "a2a"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task: Mapped[str] = mapped_column(String(100), nullable=False)
    trace_correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
