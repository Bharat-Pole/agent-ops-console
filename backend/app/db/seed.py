import json
from pathlib import Path

from app.db.connection import get_pool
from app.db.seed_embeddings import seed_embeddings_if_empty
from app.domains.agents import agents_repo
from app.domains.approvals import approvals_repo
from app.domains.audit import audit_repo
from app.domains.evaluations import eval_packs_repo
from app.domains.governance import governance_repo
from app.domains.governance.seed_catalog import PATH_DEFINITIONS, POLICY_RULES
from app.domains.models import models_repo
from app.domains.models.seed_catalog import MODEL_CATALOG
from app.domains.prompts import prompts_repo
from app.domains.tools import mcp_connectors_repo, tools_repo
from app.domains.tools.seed_catalog import MCP_CONNECTOR_CATALOG, TOOL_CATALOG_ENRICHMENT
from app.seed_data.snapshot import load_seed_snapshot

_SEED_PROMPTS_PATH = Path(__file__).parent.parent / "seed_data" / "seed_prompts.json"


async def seed_if_empty() -> None:
    pool = get_pool()
    snapshot = load_seed_snapshot()

    agent_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM agents")
    if agent_row["n"] == 0:
        for agent in snapshot["agents"]:
            await agents_repo.insert(agent)
        for approval in snapshot["approvals"]:
            await approvals_repo.insert(approval)
        for evt in snapshot["auditLog"]:
            await audit_repo.insert(evt)
        for pack in snapshot["evalPacks"]:
            await eval_packs_repo.insert(pack)
        print(
            f"[seed] inserted {len(snapshot['agents'])} agents, {len(snapshot['approvals'])} approvals, "
            f"{len(snapshot['auditLog'])} audit events, {len(snapshot['evalPacks'])} eval packs"
        )

    tool_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM tools")
    if tool_row["n"] == 0:
        for tool in snapshot["tools"]:
            await tools_repo.insert(tool)
        print(f"[seed] inserted {len(snapshot['tools'])} tools")

    # Backfill richer catalog metadata onto the (already-seeded, possibly from
    # an older schema) tool rows — runs regardless of the count above, keyed
    # on whether a row is still missing its description, so it's idempotent.
    stale_tools = await pool.fetch("SELECT id FROM tools WHERE description = ''")
    backfilled = 0
    for row in stale_tools:
        enrichment = TOOL_CATALOG_ENRICHMENT.get(row["id"])
        if enrichment:
            await tools_repo.update_fields(row["id"], enrichment)
            await pool.execute("UPDATE tools SET schema_json = $2 WHERE id = $1", row["id"], enrichment["schema"])
            backfilled += 1
    if backfilled:
        print(f"[seed] backfilled catalog metadata for {backfilled} tools")

    connector_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM mcp_connectors")
    if connector_row["n"] == 0:
        for connector in MCP_CONNECTOR_CATALOG:
            await mcp_connectors_repo.insert(connector)
        print(f"[seed] inserted {len(MCP_CONNECTOR_CATALOG)} MCP connectors")

    model_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM models")
    if model_row["n"] == 0:
        for model in MODEL_CATALOG:
            await models_repo.insert(model)
        print(f"[seed] inserted {len(MODEL_CATALOG)} models")
    else:
        # Backfill new catalog entries onto an already-seeded DB (e.g. the
        # Groq fallback model added after initial seed) — idempotent per id.
        existing_ids = {r["id"] for r in await pool.fetch("SELECT id FROM models")}
        new_models = [m for m in MODEL_CATALOG if m["id"] not in existing_ids]
        for model in new_models:
            await models_repo.insert(model)
        if new_models:
            print(f"[seed] backfilled {len(new_models)} new model(s): {[m['id'] for m in new_models]}")

    policy_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM policy_rules")
    if policy_row["n"] == 0:
        for rule in POLICY_RULES:
            await governance_repo.upsert_policy_rule(rule["capability_tier"], rule["risk_tier"], rule["governance_path"], "system")
        print(f"[seed] inserted {len(POLICY_RULES)} governance policy rules")

    path_def_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM path_definitions")
    if path_def_row["n"] == 0:
        for pd in PATH_DEFINITIONS:
            await governance_repo.insert_path_definition(pd)
        print(f"[seed] inserted {len(PATH_DEFINITIONS)} path definitions")

    prompt_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM prompts")
    if prompt_row["n"] == 0:
        with open(_SEED_PROMPTS_PATH, encoding="utf-8") as f:
            seed_prompts = json.load(f)
        for prompt in seed_prompts:
            await prompts_repo.insert(prompt)
        print(f"[seed] inserted {len(seed_prompts)} prompts")
    else:
        # Backfill body snapshots + curated tags onto prompt rows created
        # before version-snapshotting and tagging existed — idempotent, only
        # touches rows that are still missing this data, never overwrites a
        # real edit made after these fields shipped.
        with open(_SEED_PROMPTS_PATH, encoding="utf-8") as f:
            seed_by_id = {p["id"]: p for p in json.load(f)}
        existing_prompts = await prompts_repo.get_all()
        snapshotted, tagged = 0, 0
        for prompt in existing_prompts:
            history = prompt["history"]
            if history and "body" not in history[-1]:
                history = [*history[:-1], {**history[-1], "body": prompt["body"]}]
                await prompts_repo.update(prompt["id"], {"history": history})
                snapshotted += 1
            seed = seed_by_id.get(prompt["id"])
            if seed and not any([prompt["domain"], prompt["use_case"], prompt["risk_tier"], prompt["agent_type"]]):
                await prompts_repo.update(
                    prompt["id"],
                    {
                        "domain": seed.get("domain"),
                        "use_case": seed.get("use_case"),
                        "risk_tier": seed.get("risk_tier"),
                        "agent_type": seed.get("agent_type"),
                    },
                )
                tagged += 1
        if snapshotted:
            print(f"[seed] backfilled body snapshot for {snapshotted} prompt(s)")
        if tagged:
            print(f"[seed] backfilled curated tags for {tagged} prompt(s)")

    # Backfill config.data.rerank_enabled onto agents created before this field
    # existed — real chat tool-use always reranked regardless, so `True`
    # preserves each agent's actual current behavior rather than silently
    # changing it. Idempotent: only touches agents still missing the key.
    def _add_rerank_field(a):
        a["config"]["data"]["rerank_enabled"] = {
            "value": True, "value_source": "system", "verified_flag": True,
            "confidence": "high", "gap_note": None,
        }
        return a

    agents_missing_rerank = [
        a for a in await agents_repo.get_all() if "rerank_enabled" not in a["config"]["data"]
    ]
    for agent in agents_missing_rerank:
        await agents_repo.patch(agents_repo.agent_id(agent), _add_rerank_field)
    if agents_missing_rerank:
        print(f"[seed] backfilled rerank_enabled for {len(agents_missing_rerank)} agent(s)")

    await seed_embeddings_if_empty()
