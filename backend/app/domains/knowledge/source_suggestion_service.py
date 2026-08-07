import json
from typing import Any

from app.domains.chat.llm_gateway import complete_text, is_llm_configured
from app.domains.knowledge import knowledge_sources_repo
from app.env import env

# Cheap, fast model — this is a lightweight relevance-ranking call over a
# short source list, not a task that benefits from a bigger model. Falls back
# to Groq's free tier automatically (llm_gateway) if Anthropic fails.
RANKING_MODEL = env.ANTHROPIC_MODEL_MINIMAL


async def suggest_sources(objective: str) -> list[dict[str, Any]]:
    """Real LLM call ranking existing knowledge sources by relevance to an
    agent's stated objective (Onboarding Phase 1) — was entirely absent;
    source selection was 100% manual. Raises on any real failure (e.g.
    exhausted API credits, with no free fallback configured either) rather
    than returning a fabricated ranking."""
    objective = (objective or "").strip()
    if not objective:
        return []

    sources = await knowledge_sources_repo.get_all()
    candidates = [s for s in sources if s["lifecycle"] != "retired" and s["status"] == "ready"]
    if not candidates:
        return []

    if not is_llm_configured():
        raise RuntimeError("Neither ANTHROPIC_API_KEY nor GROQ_API_KEY is configured — cannot rank sources.")

    listing = "\n".join(
        f"- {s['id']}: \"{s['name']}\" (domain: {s.get('domain') or 'none'}, "
        f"tags: {', '.join(s.get('tags') or []) or 'none'})"
        for s in candidates
    )
    prompt = (
        f"Agent objective:\n{objective}\n\n"
        f"Available knowledge sources:\n{listing}\n\n"
        "Which of these sources (if any) would this agent plausibly need to answer questions "
        "grounded in its objective? Respond with ONLY a JSON array, most relevant first, each item "
        '{"source_id": "...", "relevance": "high"|"medium"|"low", "reason": "one short sentence"}. '
        "Omit sources with no plausible relevance. Respond with [] if none are relevant. No prose, JSON only."
    )

    raw = (await complete_text(
        system="You rank knowledge sources by relevance to an agent's objective. Respond with strict JSON only.",
        user=prompt,
        max_tokens=600,
        anthropic_model=RANKING_MODEL,
    )).strip()
    # Models sometimes wrap JSON in a fenced code block despite instructions.
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    valid_ids = {s["id"] for s in candidates}
    name_by_id = {s["id"]: s["name"] for s in candidates}
    result = []
    for item in parsed:
        if not isinstance(item, dict) or item.get("source_id") not in valid_ids:
            continue  # never trust a model-hallucinated id — only real, existing sources surface
        result.append(
            {
                "source_id": item["source_id"],
                "name": name_by_id[item["source_id"]],
                "relevance": item.get("relevance", "medium"),
                "reason": item.get("reason", ""),
            }
        )
    return result
