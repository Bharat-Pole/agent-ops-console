import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.audit import audit_repo
from app.domains.prompts import prompts_repo
from app.domains.chat.llm_gateway import complete_text, is_llm_configured

KIND_GUIDANCE = {
    "system": "a system prompt establishing the agent's role, scope, and behavior",
    "user_template": "a user prompt template shaping how end-user requests are framed before reaching the agent",
    "task": "a task prompt describing a specific job the agent performs and its expected output",
    "persona": "a role/persona prompt defining the agent's voice, tone, and point of view",
    "tool_use": "tool-use instructions describing when and how the agent should invoke its bound tools",
    "citation": "a citation-rules instruction describing how the agent must ground and cite claims",
    "template": "a response-format template the agent's output must follow",
    "safety": "a safety/guardrail instruction set constraining what the agent must refuse to do",
    "refusal": "a refusal instruction defining exactly how the agent must decline out-of-scope or disallowed requests",
    "escalation": "an escalation instruction defining when and how the agent hands off to a human",
    "stop_condition": "a stop-condition instruction defining when the agent must halt a task rather than continue",
}

FALLBACK_BODY = "[Draft] Describe the {kind} instructions for this {category} here. (AI generation unavailable — neither ANTHROPIC_API_KEY nor GROQ_API_KEY is configured.)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _today() -> str:
    return _now_iso()[:10]


def _bump_version(v: str) -> str:
    m = re.match(r"^v(\d+)(?:\.(\d+))?$", v)
    if not m:
        return v + "-next"
    if m.group(2) is not None:
        return f"v{m.group(1)}.{int(m.group(2)) + 1}"
    return f"v{int(m.group(1)) + 1}"


def _derive_name(kind: str, context: dict[str, Any]) -> str:
    base = (context.get("agent_name") or context.get("objective") or "New Agent").strip()
    if len(base) > 60:
        base = base[:57] + "..."
    return f"{base} — {kind}"


async def generate_body(kind: str, category: str, context: dict[str, Any]) -> str:
    if not is_llm_configured():
        return FALLBACK_BODY.format(kind=kind, category=category)

    objective = context.get("objective") or ""
    audience = context.get("audience") or ""
    tools = ", ".join(context.get("tools") or []) or "none specified"
    data_sources = ", ".join(context.get("data_sources") or []) or "none specified"
    user_instruction = (context.get("user_instruction") or "").strip()

    system = (
        "You draft short, precise governed prompt assets for an enterprise agent "
        "governance platform. Output only the prompt body text — no preamble, no markdown fences."
    )
    instruction_line = (
        f"The user gave this specific instruction for what the prompt should say — treat it as the "
        f"primary source of truth and rephrase/tighten it rather than ignoring it: \"{user_instruction}\"\n"
        if user_instruction
        else "The user did not provide specific instructions, so draft this from the agent context below.\n"
    )
    user = (
        f"Draft {KIND_GUIDANCE.get(kind, 'a prompt')} for a {category}, serving this objective: {objective}\n"
        f"{instruction_line}"
        f"Intended audience: {audience}\nAvailable tools: {tools}\nData sources: {data_sources}\n"
        "Keep it under 150 words. Include an explicit advisory-only boundary if this is a system or safety prompt."
    )
    try:
        text = (await complete_text(system, user)).strip()
        return text or FALLBACK_BODY.format(kind=kind, category=category)
    except Exception as err:
        print("[prompt_generation]", err)
        return FALLBACK_BODY.format(kind=kind, category=category)


async def generate_draft(kind: str, category: str, context: dict[str, Any]) -> dict[str, str]:
    body = await generate_body(kind, category, context)
    return {"name": _derive_name(kind, context), "body": body}


async def create_prompt(body: dict[str, Any]) -> dict[str, Any]:
    source = body.get("source") or "manual"
    note = "Created." if source == "manual" else "Drafted by AI, reviewed and saved."
    prompt_body = body.get("body") or ""
    prompt = {
        "id": body.get("id") or f"prompt-{uuid.uuid4().hex[:8]}",
        "version": "v1",
        "name": body.get("name") or "New Prompt",
        "kind": body.get("kind") or "template",
        "category": body.get("category") or "agent",
        "source": source,
        "generated_from": body.get("generated_from"),
        "body": prompt_body,
        "status": "draft",
        "owner": body.get("owner") or "unknown@brightspeed.com",
        "used_by": [],
        "history": [{"version": "v1", "date": _today(), "note": note, "body": prompt_body}],
        "domain": body.get("domain"),
        "use_case": body.get("use_case"),
        "risk_tier": body.get("risk_tier"),
        "agent_type": body.get("agent_type"),
        "citation_format": body.get("citation_format"),
    }
    await prompts_repo.insert(prompt)
    return prompt


async def generate_prompt(body: dict[str, Any]) -> dict[str, Any]:
    kind = body.get("kind") or "template"
    category = body.get("category") or "agent"
    context = body.get("context") or {}
    text = await generate_body(kind, category, context)
    prompt = {
        "id": body.get("id") or f"prompt-{uuid.uuid4().hex[:8]}",
        "version": "v1",
        "name": body.get("name") or f"AI-drafted {kind} prompt",
        "kind": kind,
        "category": category,
        "source": "llm_generated",
        "generated_from": context.get("agent_id"),
        "body": text,
        "status": "draft",
        "owner": body.get("owner") or "engine@brightspeed.com",
        "used_by": [],
        "history": [{"version": "v1", "date": _today(), "note": "Drafted by AI.", "body": text}],
        "domain": body.get("domain"),
        "use_case": body.get("use_case"),
        "risk_tier": body.get("risk_tier"),
        "agent_type": body.get("agent_type"),
        "citation_format": body.get("citation_format"),
    }
    await prompts_repo.insert(prompt)
    return prompt


async def new_version(prompt_id: str) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    nv = _bump_version(existing["version"])
    # Freeze the outgoing version's final body into its own history entry —
    # it's about to stop being "current" and editable, so this is the last
    # moment its real text is guaranteed to still match `body`.
    history = _freeze_last_snapshot(existing["history"], existing["version"], existing["body"])
    history = [*history, {"version": nv, "date": _today(), "note": "New version drafted.", "body": existing["body"]}]
    return await prompts_repo.update(prompt_id, {"version": nv, "status": "draft", "history": history})


def _freeze_last_snapshot(history: list[dict[str, Any]], version: str, body: str) -> list[dict[str, Any]]:
    if history and history[-1].get("version") == version:
        history = [*history[:-1], {**history[-1], "body": body}]
    return history


async def update_fields(prompt_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    fields = {
        k: v for k, v in patch.items()
        if k in (
            "name", "kind", "category", "body", "owner", "domain", "use_case", "risk_tier", "agent_type",
            "citation_format",
        )
    }
    if "body" in fields:
        fields["history"] = _freeze_last_snapshot(existing["history"], existing["version"], fields["body"])
    return await prompts_repo.update(prompt_id, fields)


async def compare_versions(prompt_id: str, version_a: str, version_b: str) -> dict[str, Any]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        raise ValueError("Prompt not found.")
    entries = {h["version"]: h for h in existing["history"]}

    def _snapshot(v: str) -> dict[str, Any]:
        entry = entries.get(v)
        if entry is None:
            raise ValueError(f"Version {v} not found in this prompt's history.")
        if "body" not in entry:
            raise ValueError(f"No stored snapshot for version {v} — it predates version snapshotting.")
        return {"version": v, "date": entry["date"], "body": entry["body"]}

    return {"a": _snapshot(version_a), "b": _snapshot(version_b)}


async def rollback_to(prompt_id: str, target_version: str, actor_persona: str) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    entries = {h["version"]: h for h in existing["history"]}
    target = entries.get(target_version)
    if target is None:
        raise ValueError(f"Version {target_version} not found in this prompt's history.")
    if "body" not in target:
        raise ValueError(f"No stored snapshot for version {target_version} — it predates version snapshotting.")

    nv = _bump_version(existing["version"])
    history = _freeze_last_snapshot(existing["history"], existing["version"], existing["body"])
    history = [
        *history,
        {"version": nv, "date": _today(), "note": f"Rolled back to {target_version}.", "body": target["body"]},
    ]
    prompt = await prompts_repo.update(
        prompt_id, {"version": nv, "status": "draft", "body": target["body"], "history": history}
    )
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "rollback",
            "entity_type": "prompt",
            "entity_id": prompt_id,
            "detail": f"Rolled back {existing['name']} from {existing['version']} to {target_version} (as new {nv}).",
        }
    )
    return {"prompt": prompt, "auditEvent": audit_event}


async def decide(prompt_id: str, decision: str, actor_persona: str) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    status = "approved" if decision == "approved" else existing["status"]
    prompt = await prompts_repo.update(prompt_id, {"status": status})
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "approve" if decision == "approved" else "reject",
            "entity_type": "prompt",
            "entity_id": prompt_id,
            "detail": f"{'Approved' if decision == 'approved' else 'Rejected'} {existing['name']} {existing['version']}.",
        }
    )
    return {"prompt": prompt, "auditEvent": audit_event}


async def export_approved_pack(domain: Optional[str] = None, agent_type: Optional[str] = None) -> dict[str, Any]:
    prompts = await prompts_repo.get_all()
    approved = [p for p in prompts if p["status"] == "approved"]
    if domain:
        approved = [p for p in approved if p.get("domain") == domain]
    if agent_type:
        approved = [p for p in approved if p.get("agent_type") == agent_type]
    return {
        "generated_at": _now_iso(),
        "filters": {"domain": domain, "agent_type": agent_type},
        "count": len(approved),
        "prompts": approved,
    }


async def delete_prompt(prompt_id: str, actor_persona: str) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    if existing["used_by"]:
        raise ValueError("Prompt is referenced by an agent — deprecate instead of deleting.")
    deleted = await prompts_repo.delete_by_id(prompt_id)
    if not deleted:
        return None
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "delete",
            "entity_type": "prompt",
            "entity_id": prompt_id,
            "detail": f"Deleted {existing['name']} {existing['version']}.",
        }
    )
    return {"auditEvent": audit_event}


async def deprecate(prompt_id: str, actor_persona: str) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    prompt = await prompts_repo.update(prompt_id, {"status": "deprecated"})
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "deprecate",
            "entity_type": "prompt",
            "entity_id": prompt_id,
            "detail": f"Deprecated {existing['name']} {existing['version']}.",
        }
    )
    return {"prompt": prompt, "auditEvent": audit_event}
