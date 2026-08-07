"""Deployment + channels (Pass 7). A deployment is an IMMUTABLE manifest:
the workflow graph with asset pins baked into node configs (prompt content
frozen, tool versions pinned — runtime policy checks still apply). The REST
channel authenticates with per-access-group hashed API keys and enforces a
per-deployment rate limit. Rollback re-activates a prior manifest as a NEW
record — history is never rewritten.
"""
from __future__ import annotations

import hashlib
import re
import secrets as py_secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events, policy
from ..audit import audit
from ..auth.deps import current_user_dep, require_role
from ..db import get_db
from ..engine import runner
from ..models import (
    AccessGroup, AgentControlRecord, ApiKey, AssetStatus, Deployment, PromptPack,
    PromptVersion, Role, RunHitl, RunStatus, ToolRecord, User, Workflow,
    WorkflowRun, WorkflowStatus, WorkflowVersion, utcnow,
)

router = APIRouter(tags=["deployment"])

_DEPLOY_ROLES = (Role.agent_owner, Role.ai_engineer, Role.platform_admin)
_KEY_ROLES = (Role.ai_engineer, Role.platform_admin)


# ---- manifest ---------------------------------------------------------------

def build_manifest(db: Session, version: WorkflowVersion) -> dict:
    """Freeze the graph with asset pins in node configs. RAG pipelines are
    pinned by name only — knowledge content evolving is a feature (freshness),
    recorded as such."""
    graph = {"nodes": [dict(n) for n in version.graph.get("nodes", [])],
             "edges": [dict(e) for e in version.graph.get("edges", [])]}
    pins: dict = {"prompts": {}, "tools": {}, "rag_note": "pipelines pinned by name; corpus refreshes by design"}
    for node in graph["nodes"]:
        config = dict(node.get("config") or {})
        if node.get("type") == "prompt" and config.get("pack_ref"):
            pack = db.scalars(select(PromptPack).where(PromptPack.slug == config["pack_ref"])).first()
            approved = pack and db.scalars(select(PromptVersion).where(
                PromptVersion.pack_id == pack.id, PromptVersion.status == AssetStatus.approved)
                .order_by(PromptVersion.version.desc())).first()
            if approved:
                config["pinned_content"] = approved.content
                config["pinned_version"] = approved.version
                pins["prompts"][config["pack_ref"]] = {"version": approved.version, "id": str(approved.id)}
        if node.get("type") in ("tool_call", "mcp_call") and config.get("tool_ref"):
            tool = db.scalars(select(ToolRecord).where(
                ToolRecord.slug == config["tool_ref"], ToolRecord.status == AssetStatus.approved)
                .order_by(ToolRecord.version.desc())).first()
            if tool:
                config["pinned_tool_id"] = str(tool.id)
                pins["tools"][config["tool_ref"]] = {"version": tool.version, "id": str(tool.id),
                                                     "permission_type": tool.permission_type.value}
        node["config"] = config
    return {"graph": graph, "asset_pins": pins,
            "workflow_version": version.version, "workflow_version_id": str(version.id),
            "snapshot_at": utcnow().isoformat()}


def _payload(d: Deployment) -> dict:
    return {
        "id": str(d.id), "agent_id": str(d.agent_id), "slug": d.slug, "channel": d.channel,
        "workflow_version_id": str(d.workflow_version_id),
        "workflow_version": (d.manifest or {}).get("workflow_version"),
        "asset_pins": (d.manifest or {}).get("asset_pins"),
        "admission": d.admission, "status": d.status,
        "access_group_id": str(d.access_group_id) if d.access_group_id else None,
        "rate_limit_per_min": d.rate_limit_per_min,
        "previous_deployment_id": str(d.previous_deployment_id) if d.previous_deployment_id else None,
        "invoke_path": f"/api/deployed/{d.slug}/invoke" if d.status == "active" else None,
        "created_at": d.created_at.isoformat(),
    }


# ---- access groups + keys ---------------------------------------------------

class GroupBody(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = ""


@router.post("/api/access-groups", status_code=201)
def create_group(body: GroupBody, db: Session = Depends(get_db),
                 user: User = Depends(require_role(*_KEY_ROLES))):
    if db.scalars(select(AccessGroup).where(AccessGroup.name == body.name)).first():
        raise HTTPException(status_code=409, detail="access group exists")
    group = AccessGroup(name=body.name, description=body.description, created_by=user.id)
    db.add(group)
    db.flush()
    audit(db, user, "access_group_created", "access_group", str(group.id))
    db.commit()
    return {"id": str(group.id), "name": group.name, "description": group.description}


@router.get("/api/access-groups")
def list_groups(db: Session = Depends(get_db), _: User = Depends(current_user_dep)):
    groups = db.scalars(select(AccessGroup).order_by(AccessGroup.name)).all()
    out = []
    for g in groups:
        keys = db.scalars(select(ApiKey).where(ApiKey.group_id == g.id)).all()
        out.append({"id": str(g.id), "name": g.name, "description": g.description,
                    "keys": [{"id": str(k.id), "name": k.name, "prefix": k.prefix,
                              "revoked": k.revoked, "created_at": k.created_at.isoformat()}
                             for k in keys]})
    return out


class KeyBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)


@router.post("/api/access-groups/{group_id}/keys", status_code=201)
def create_key(group_id: uuid.UUID, body: KeyBody, db: Session = Depends(get_db),
               user: User = Depends(require_role(*_KEY_ROLES))):
    group = db.get(AccessGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="access group not found")
    plaintext = f"pk_{py_secrets.token_urlsafe(32)}"
    key = ApiKey(group_id=group.id, name=body.name,
                 key_hash=hashlib.sha256(plaintext.encode()).hexdigest(),
                 prefix=plaintext[:10], created_by=user.id)
    db.add(key)
    db.flush()
    audit(db, user, "api_key_created", "access_group", str(group.id),
          {"key_id": str(key.id), "prefix": key.prefix})  # never the key itself
    db.commit()
    return {"id": str(key.id), "name": key.name, "prefix": key.prefix,
            "api_key": plaintext,  # shown exactly ONCE; only the hash is stored
            "note": "store this now — it cannot be retrieved again"}


@router.post("/api/api-keys/{key_id}/revoke")
def revoke_key(key_id: uuid.UUID, db: Session = Depends(get_db),
               user: User = Depends(require_role(*_KEY_ROLES))):
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")
    key.revoked = True
    audit(db, user, "api_key_revoked", "access_group", str(key.group_id), {"key_id": str(key.id)})
    db.commit()
    return {"id": str(key.id), "revoked": True}


# ---- deployments ------------------------------------------------------------

class DeployBody(BaseModel):
    channel: str = Field(default="sandbox", pattern="^(sandbox|production)$")
    access_group_id: uuid.UUID | None = None
    rate_limit_per_min: int = Field(default=30, ge=1, le=600)


@router.post("/api/agents/{agent_id}/deployments", status_code=201)
def deploy(agent_id: uuid.UUID, body: DeployBody, db: Session = Depends(get_db),
           user: User = Depends(require_role(*_DEPLOY_ROLES))):
    agent = db.get(AgentControlRecord, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    version = db.scalars(
        select(WorkflowVersion).join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .where(Workflow.agent_id == agent.id, WorkflowVersion.status == WorkflowStatus.active)
    ).first()
    if version is None:
        raise HTTPException(status_code=409, detail="agent has no active workflow version")
    if body.access_group_id and db.get(AccessGroup, body.access_group_id) is None:
        raise HTTPException(status_code=404, detail="access group not found")

    decision = policy.check_deploy_admission(db, agent, version, body.channel)
    audit(db, user, "deploy_admission_checked", "agent", str(agent.id), {
        "channel": body.channel, "allowed": decision.allowed,
        "reasons": decision.reasons, "rules_version": decision.rules_version,
    })
    if not decision.allowed:
        db.commit()  # DENY audited
        raise HTTPException(status_code=403, detail={"reasons": decision.reasons})

    prior = db.scalars(select(Deployment).where(
        Deployment.agent_id == agent.id, Deployment.channel == body.channel,
        Deployment.status == "active")).first()
    if prior:
        prior.status = "superseded"

    slug = re.sub(r"[^a-z0-9-]", "", f"{agent.slug}-{body.channel}")
    deployment = Deployment(
        agent_id=agent.id, workflow_version_id=version.id, slug=slug, channel=body.channel,
        manifest=build_manifest(db, version),
        admission={"allowed": True, "reasons": decision.reasons,
                   "rules_version": decision.rules_version, "checked_at": utcnow().isoformat()},
        access_group_id=body.access_group_id, rate_limit_per_min=body.rate_limit_per_min,
        previous_deployment_id=prior.id if prior else None, created_by=user.id,
    )
    db.add(deployment)
    db.flush()
    audit(db, user, "deployment_created", "deployment", str(deployment.id),
          {"agent_id": str(agent.id), "channel": body.channel, "slug": slug})
    db.commit()
    events.emit("deployment.activated", {"deployment_id": str(deployment.id), "slug": slug})
    return _payload(deployment)


@router.get("/api/agents/{agent_id}/deployments")
def list_deployments(agent_id: uuid.UUID, db: Session = Depends(get_db),
                     _: User = Depends(current_user_dep)):
    rows = db.scalars(select(Deployment).where(Deployment.agent_id == agent_id)
                      .order_by(Deployment.created_at.desc())).all()
    return [_payload(d) for d in rows]


@router.post("/api/deployments/{deployment_id}/rollback", status_code=201)
def rollback(deployment_id: uuid.UUID, db: Session = Depends(get_db),
             user: User = Depends(require_role(*_DEPLOY_ROLES))):
    target = db.get(Deployment, deployment_id)
    if target is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    if target.status == "active":
        raise HTTPException(status_code=409, detail="deployment is already active")
    current = db.scalars(select(Deployment).where(
        Deployment.agent_id == target.agent_id, Deployment.channel == target.channel,
        Deployment.status == "active")).first()
    if current:
        current.status = "rolled_back"
    restored = Deployment(
        agent_id=target.agent_id, workflow_version_id=target.workflow_version_id,
        slug=target.slug, channel=target.channel,
        manifest=target.manifest,  # the frozen manifest, verbatim
        admission={"note": f"rollback of {target.id} — original admission preserved in that record",
                   "rolled_back_from": str(current.id) if current else None},
        access_group_id=target.access_group_id, rate_limit_per_min=target.rate_limit_per_min,
        previous_deployment_id=current.id if current else None, created_by=user.id,
    )
    db.add(restored)
    db.flush()
    audit(db, user, "deployment_rolled_back", "deployment", str(restored.id),
          {"restored_manifest_of": str(target.id)})
    db.commit()
    return _payload(restored)


# ---- REST channel (API-key auth — NO session) -------------------------------

class InvokeBody(BaseModel):
    input: str = Field(min_length=1, max_length=8000)


@router.post("/api/deployed/{slug}/invoke")
def invoke(slug: str, body: InvokeBody, db: Session = Depends(get_db),
           x_api_key: str | None = Header(default=None)):
    deployment = db.scalars(select(Deployment).where(
        Deployment.slug == slug, Deployment.status == "active")).first()
    if deployment is None:
        raise HTTPException(status_code=404, detail="no active deployment at this path")

    if deployment.access_group_id is None:
        raise HTTPException(status_code=403, detail="deployment has no access group — no keys can reach it")
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    key = db.scalars(select(ApiKey).where(
        ApiKey.key_hash == hashlib.sha256(x_api_key.encode()).hexdigest(),
        ApiKey.revoked.is_(False))).first()
    if key is None or key.group_id != deployment.access_group_id:
        raise HTTPException(status_code=401, detail="invalid API key for this deployment")

    window_start = utcnow() - timedelta(seconds=60)
    recent = db.scalar(select(func.count(WorkflowRun.id)).where(
        WorkflowRun.agent_id == deployment.agent_id,
        WorkflowRun.mode == "deployed",
        WorkflowRun.started_at >= window_start)) or 0
    if recent >= deployment.rate_limit_per_min:
        raise HTTPException(status_code=429, detail=f"rate limit {deployment.rate_limit_per_min}/min exceeded")

    run = WorkflowRun(
        agent_id=deployment.agent_id, workflow_version_id=deployment.workflow_version_id,
        mode="deployed",
        input={"text": body.input, "deployment_id": str(deployment.id),
               "channel": deployment.channel, "key_prefix": key.prefix},
        created_by=deployment.created_by,  # attribution: the deployer; caller identified by key prefix
    )
    db.add(run)
    db.flush()
    audit(db, None, "deployed_invoke", "deployment", str(deployment.id),
          {"run_id": str(run.id), "key_prefix": key.prefix})
    db.commit()

    runner.start_run(db, run, (deployment.manifest or {}).get("graph") or {}, body.input)
    db.commit()

    response: dict = {"run_id": str(run.id), "status": run.status.value}
    if run.status == RunStatus.completed:
        response["output"] = (run.output or {}).get("final_output")
    elif run.status == RunStatus.failed:
        response["error"] = run.error
    elif run.status == RunStatus.paused_hitl:
        pending = db.scalars(select(RunHitl).where(
            RunHitl.run_id == run.id, RunHitl.status == "pending")).first()
        response["note"] = "run paused for human approval inside the platform"
        response["hitl_id"] = str(pending.id) if pending else None
    return response
