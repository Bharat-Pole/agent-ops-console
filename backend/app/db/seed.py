from app.db.connection import get_pool
from app.db.seed_embeddings import seed_embeddings_if_empty
from app.repositories import agents_repo, approvals_repo, audit_repo, eval_packs_repo, tools_repo
from app.seed_data.snapshot import load_seed_snapshot


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

    await seed_embeddings_if_empty()
