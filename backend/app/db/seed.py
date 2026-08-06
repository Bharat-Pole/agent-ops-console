from app.db.connection import get_pool
from app.db.seed_embeddings import seed_embeddings_if_empty
from app.repositories import (
    agents_repo,
    approvals_repo,
    audit_repo,
    connector_backlog_repo,
    connectors_repo,
    eval_packs_repo,
    tools_repo,
)
from app.seed_data.backlog_seed import BACKLOG_SEED
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

    # Connectors seed independently of tools so an existing dev DB (which has
    # tools but predates the connectors table) still gets populated on boot.
    connector_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM connectors")
    if connector_row["n"] == 0:
        for connector in snapshot.get("connectors", []):
            await connectors_repo.insert(connector)
        print(f"[seed] inserted {len(snapshot.get('connectors', []))} connectors")

    # Seeds independently of everything else, same reasoning as connectors: an
    # existing dev DB predates this table and should still get the assessment.
    # Lives in a .py rather than seed_snapshot.json because it has no TS
    # counterpart — the backlog is server-side research, not client seed data.
    backlog_row = await pool.fetchrow("SELECT COUNT(*)::int AS n FROM connector_backlog")
    if backlog_row["n"] == 0:
        for entry in BACKLOG_SEED:
            await connector_backlog_repo.insert(entry)
        print(f"[seed] inserted {len(BACKLOG_SEED)} connector backlog items")

    await seed_embeddings_if_empty()
