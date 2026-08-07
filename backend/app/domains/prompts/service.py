import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.audit import audit_repo
from app.domains.prompts import prompts_repo
from app.domains.chat.llm_gateway import complete_text, is_llm_configured

KIND_GUIDANCE = {
    "system": "a system prompt establishing the agent's role, scope, and behavior",
    "safety": "a safety/guardrail instruction set constraining what the agent must refuse to do",
    "citation": "a citation-rules instruction describing how the agent must ground and cite claims",
    "template": "a response-format template the agent's output must follow",
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
    prompt = {
        "id": body.get("id") or f"prompt-{uuid.uuid4().hex[:8]}",
        "version": "v1",
        "name": body.get("name") or "New Prompt",
        "kind": body.get("kind") or "template",
        "category": body.get("category") or "agent",
        "source": source,
        "generated_from": body.get("generated_from"),
        "body": body.get("body") or "",
        "status": "draft",
        "owner": body.get("owner") or "unknown@brightspeed.com",
        "used_by": [],
        "history": [{"version": "v1", "date": _today(), "note": note}],
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
        "history": [{"version": "v1", "date": _today(), "note": "Drafted by AI."}],
    }
    await prompts_repo.insert(prompt)
    return prompt


async def new_version(prompt_id: str) -> Optional[dict[str, Any]]:
    existing = await prompts_repo.get_by_id(prompt_id)
    if existing is None:
        return None
    nv = _bump_version(existing["version"])
    history = [*existing["history"], {"version": nv, "date": _today(), "note": "New version drafted."}]
    return await prompts_repo.update(prompt_id, {"version": nv, "status": "draft", "history": history})


async def update_fields(prompt_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    fields = {k: v for k, v in patch.items() if k in ("name", "kind", "category", "body", "owner")}
    return await prompts_repo.update(prompt_id, fields)


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
