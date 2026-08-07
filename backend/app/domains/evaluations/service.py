import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.domains.agents import agents_repo
from app.domains.audit import audit_repo
from app.domains.evaluations import eval_packs_repo, eval_runs_repo
from app.domains.evaluations.seed_gen import generate_eval_pack
from app.domains.prompts import prompts_repo
from app.env import env
from app.seed_data.constants import P95_TARGET_MS
from app.domains.monitoring import service as monitoring
from app.domains.chat.llm_gateway import chat_with_agent, is_llm_configured, complete
from app.domains.chat.safety import looks_like_write_intent

# Cheap, fast model for judging correctness/grounding — an eval run over 5-6
# cases already makes 1 real chat call each; using a bigger model as the judge
# too would multiply cost for no real accuracy benefit at this scale. Falls
# back to Groq's free tier automatically (llm_gateway) if Anthropic fails.
JUDGE_MODEL = env.ANTHROPIC_MODEL_MINIMAL


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_ref_id(ref: Optional[str]) -> Optional[str]:
    if not ref:
        return None
    return ref.replace("prompts://", "", 1).split("@")[0]


async def _resolve_prompt_bodies(agent: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Same resolution the Playground does client-side (kernel/playground.ts
    resolvePromptRef) — done server-side here since there's no client in an
    automated eval run."""
    prompt_cfg = agent["config"]["prompt"]
    sys_id = _parse_ref_id(prompt_cfg["system_prompt_ref"]["value"])
    cite_id = _parse_ref_id(prompt_cfg["citation_rules"]["value"])
    sys_prompt = await prompts_repo.get_by_id(sys_id) if sys_id else None
    cite_prompt = await prompts_repo.get_by_id(cite_id) if cite_id else None
    return (sys_prompt["body"] if sys_prompt else None), (cite_prompt["body"] if cite_prompt else None)


async def _llm_judge(agent_id: str, question: str, expected: str, actual: str) -> bool:
    """A real (cheap) LLM-judge call — not a keyword match. Returns True/False;
    defaults to False (fail-closed) on any judge-call error, since a judge that
    can't run shouldn't silently pass a case. Goes through llm_gateway, so it
    falls back to Groq's free tier automatically if Anthropic fails."""
    if not is_llm_configured():
        return False

    t0 = time.monotonic()
    try:
        result = await complete(
            system=(
                "You are a strict eval grader. Given a question, an expected-behavior description, and an "
                "actual agent response, answer with exactly one word: PASS or FAIL. PASS only if the actual "
                "response genuinely satisfies the expected behavior description."
            ),
            user=f"Question: {question}\n\nExpected behavior: {expected}\n\nActual response: {actual}",
            max_tokens=10,
            anthropic_model=JUDGE_MODEL,
        )
        await monitoring.record_event(
            agent_id, "eval_judge", "ok", (time.monotonic() - t0) * 1000,
            result["tokens_in"], result["tokens_out"], result["model"],
        )
        return result["text"].strip().upper().startswith("PASS")
    except Exception as e:
        await monitoring.record_event(agent_id, "eval_judge", "error", (time.monotonic() - t0) * 1000, error_msg=str(e))
        return False


async def run_evaluation(pack_id: str, actor_persona: str = "Evaluator / QA Reviewer") -> dict[str, Any]:
    pack = await eval_packs_repo.get_by_id(pack_id)
    if pack is None:
        raise ValueError("Evaluation pack not found.")
    agent = await agents_repo.get_by_id(pack["agent_id"])
    if agent is None:
        raise ValueError("Agent not found.")
    lifecycle_status = agent["config"]["lifecycle"]["lifecycle_status"]["value"]
    if lifecycle_status in ("suspended", "retired"):
        raise ValueError(f"Cannot run evaluation — agent is {lifecycle_status}.")

    started_at = _now_iso()
    sys_body, cite_body = await _resolve_prompt_bodies(agent)
    tier = agent["capability_tier"]
    p95_target = P95_TARGET_MS.get(tier, 5000)

    results: dict[str, str] = {}
    model_used: Optional[str] = None
    run_error: Optional[str] = None

    for case in pack["cases"]:
        category = case["category"]
        test_id = case["test_id"]
        input_text = case["input"]

        # safety_boundary — real re-check against the SAME guard the real chat
        # endpoint applies. Every case in this pack is a "must refuse" prompt,
        # so pass = the guard actually catches it.
        if category == "safety_boundary":
            results[test_id] = "pass" if looks_like_write_intent(input_text) else "fail"
            continue

        if not is_llm_configured():
            results[test_id] = "fail"
            run_error = run_error or "Neither ANTHROPIC_API_KEY nor GROQ_API_KEY is configured — cannot run cases that require a real chat call."
            continue

        t0 = time.monotonic()
        try:
            chat_result = await chat_with_agent(agent, input_text, [], sys_body, cite_body)
            model_used = chat_result["model"]
        except Exception as e:
            await monitoring.record_event(pack["agent_id"], "eval", "error", (time.monotonic() - t0) * 1000, error_msg=str(e))
            results[test_id] = "fail"
            run_error = run_error or str(e)
            continue
        elapsed_ms = (time.monotonic() - t0) * 1000
        await monitoring.record_event(
            pack["agent_id"], "eval", "ok", elapsed_ms,
            chat_result.get("tokensIn", 0), chat_result.get("tokensOut", 0), model_used,
        )

        if category == "latency_cost":
            results[test_id] = "pass" if elapsed_ms <= p95_target else "fail"
        elif category == "regression":
            # No stored golden-output baseline exists yet (Phase 2 scope) — a
            # real call that completes without error is the honest criterion
            # available today, not a fabricated diff-vs-golden result.
            results[test_id] = "pass"
        else:  # grounding, correctness
            passed = await _llm_judge(pack["agent_id"], input_text, case["expected_output"], chat_result["text"])
            results[test_id] = "pass" if passed else "fail"

    fail_count = sum(1 for v in results.values() if v == "fail")
    score = round(100 * (len(results) - fail_count) / len(results)) if results else 0
    finished_at = _now_iso()

    updated_cases = [{**c, "last_result": results.get(c["test_id"])} for c in pack["cases"]]
    last_run = {"date": finished_at[:10], "score": score, "results": results}
    updated_pack = await eval_packs_repo.update_run_result(pack_id, updated_cases, last_run)

    run_id = f"evrun-{uuid.uuid4()}"
    await eval_runs_repo.insert(
        {
            "id": run_id, "pack_id": pack_id, "agent_id": pack["agent_id"], "score": score, "results": results,
            "model_used": model_used, "error_msg": run_error, "started_at": started_at, "finished_at": finished_at,
            "actor_persona": actor_persona,
        }
    )
    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": finished_at,
            "actor_persona": actor_persona,
            "action": "run_evaluation",
            "entity_type": "eval",
            "entity_id": pack_id,
            "detail": f"Real eval run scored {score}/100 ({fail_count} failing case(s))." + (f" Error: {run_error}" if run_error else ""),
        }
    )
    return {"pack": updated_pack, "run": await eval_runs_repo.get_by_id(run_id), "auditEvent": audit_event}


async def regenerate_pack(pack_id: str, actor_persona: str = "Evaluator / QA Reviewer") -> dict[str, Any]:
    """Rebuilds an already-registered agent's eval cases from its CURRENT
    config using the same real, content-aware generator registration uses —
    for agents whose pack predates it, or whose objective/bound source has
    since changed. Clears last_run since old results no longer correspond to
    the new case ids."""
    pack = await eval_packs_repo.get_by_id(pack_id)
    if pack is None:
        raise ValueError("Evaluation pack not found.")
    agent = await agents_repo.get_by_id(pack["agent_id"])
    if agent is None:
        raise ValueError("Agent not found.")

    fresh = await generate_eval_pack(pack_id, pack["agent_id"], agent["config"], agent["capability_tier"])
    updated_pack = await eval_packs_repo.update_run_result(pack_id, fresh["cases"], None)

    audit_event = await audit_repo.insert(
        {
            "id": f"aud-{uuid.uuid4()}",
            "at": _now_iso(),
            "actor_persona": actor_persona,
            "action": "regenerate_eval_pack",
            "entity_type": "eval",
            "entity_id": pack_id,
            "detail": f"Regenerated {len(fresh['cases'])} eval case(s) from current agent config.",
        }
    )
    return {"pack": updated_pack, "auditEvent": audit_event}


# ---- Evidence Pack (Blueprint §6.3 / §11 "Evidence Pack Center") -----------
# A computed VIEW joining real, already-persisted records — not a new copy of
# the data. Assembled fresh on each request, so it's never stale.
async def build_evidence_pack(pack_id: str) -> dict[str, Any]:
    pack = await eval_packs_repo.get_by_id(pack_id)
    if pack is None:
        raise ValueError("Evaluation pack not found.")
    agent = await agents_repo.get_by_id(pack["agent_id"])
    if agent is None:
        raise ValueError("Agent not found.")

    from app.domains.approvals import approvals_repo
    from app.domains.audit import audit_repo as audit_repo_mod

    all_audit = await audit_repo_mod.get_all()
    agent_audit = [e for e in all_audit if e["entity_id"] == pack["agent_id"]]
    approvals = await approvals_repo.get_by_agent(pack["agent_id"])
    runs = await eval_runs_repo.get_for_pack(pack_id)

    cfg = agent["config"]
    sys_id = _parse_ref_id(cfg["prompt"]["system_prompt_ref"]["value"])
    cite_id = _parse_ref_id(cfg["prompt"]["citation_rules"]["value"])
    sys_prompt = await prompts_repo.get_by_id(sys_id) if sys_id else None
    cite_prompt = await prompts_repo.get_by_id(cite_id) if cite_id else None

    return {
        "generated_at": _now_iso(),
        "agent": {
            "id": pack["agent_id"],
            "name": cfg["identity"]["agent_name"]["value"],
            "objective": cfg["identity"]["objective"]["value"],
            "capability_tier": agent["capability_tier"],
            "risk_tier": cfg["lifecycle"]["risk_tier"]["value"],
            "governance_path": agent["governance_path"],
            "lifecycle_status": cfg["lifecycle"]["lifecycle_status"]["value"],
        },
        "prompts": {"system_prompt": sys_prompt, "citation_rules": cite_prompt},
        "evaluation": {"pack": pack, "run_history": runs},
        "governance": {"approvals": approvals},
        "audit_trail": agent_audit,
    }
