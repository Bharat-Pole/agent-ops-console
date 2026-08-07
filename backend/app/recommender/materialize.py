"""Acceptance → materialization (Pass 2 → Pass 3 handoff): accepting a
recommendation component creates a DRAFT asset in the proper registry — never
bulk, never auto-approved, always through the asset's own approval workflow.

What cannot be honestly materialized is not: knowledge needs a real file
upload, models are admin-governed catalog entries, connectors need a real
endpoint. Those return guidance instead of records.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PromptPack, PromptVersion, ToolRecord, User


def _slug(text: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:56] or fallback


def materialize_component(db: Session, item: dict, user: User) -> dict:
    """item = a recommendation item (kind component_*). Returns
    {materialized: bool, asset_type, asset_id?, guidance?}. Idempotence is the
    caller's job (it stores the result on the item)."""
    kind = item.get("kind", "")
    detail = item.get("detail") or {}
    name = str(detail.get("name") or "unnamed")
    purpose = str(detail.get("purpose") or "")

    if kind == "component_tool":
        slug = _slug(name, "tool")
        existing = db.scalars(select(ToolRecord).where(ToolRecord.slug == slug)).first()
        if existing:
            return {"materialized": False, "asset_type": "tool",
                    "guidance": f"tool slug {slug!r} already exists — review it instead of duplicating"}
        tool = ToolRecord(
            slug=slug, name=name, description=purpose,
            business_purpose=f"Materialized from accepted recommendation item {item.get('id')}",
            implementation={"kind": "none", "config": {}},  # honest not-connected stub
            source="materialized", owner_id=user.id,
        )
        db.add(tool)
        db.flush()
        return {"materialized": True, "asset_type": "tool", "asset_id": str(tool.id),
                "note": "draft created with implementation kind 'none' — declare the real binding before approval"}

    if kind == "component_prompt":
        slug = _slug(name, "prompt")
        existing = db.scalars(select(PromptPack).where(PromptPack.slug == slug)).first()
        if existing:
            return {"materialized": False, "asset_type": "prompt",
                    "guidance": f"prompt slug {slug!r} already exists — review it instead of duplicating"}
        pack = PromptPack(slug=slug, name=name, prompt_type="task",
                          description=purpose, owner_id=user.id)
        db.add(pack)
        db.flush()
        scaffold = (
            f"# {name} (DRAFT scaffold — materialized from an accepted recommendation)\n"
            f"# Purpose: {purpose or 'describe the task'}\n\n"
            "Write the actual prompt content here. This scaffold is not usable content\n"
            "and will not pass governance review as-is."
        )
        v1 = PromptVersion(pack_id=pack.id, version=1, content=scaffold,
                           notes="materialized scaffold", created_by=user.id)
        db.add(v1)
        db.flush()
        return {"materialized": True, "asset_type": "prompt", "asset_id": str(pack.id),
                "note": "draft pack + scaffold v1 created — author real content before submitting for approval"}

    if kind == "component_knowledge":
        return {"materialized": False, "asset_type": "knowledge",
                "guidance": "knowledge sources require a real file upload (Asset Studio → Knowledge → Upload); "
                            "nothing was fabricated"}
    if kind == "component_model":
        return {"materialized": False, "asset_type": "model",
                "guidance": "models are selected from the admin-governed catalog — bind one via agent bindings"}
    if kind == "component_connector":
        return {"materialized": False, "asset_type": "connector",
                "guidance": "MCP connectors require a real endpoint — register one under Asset Studio → MCP"}
    return {"materialized": False, "asset_type": None, "guidance": f"item kind {kind!r} does not materialize"}
