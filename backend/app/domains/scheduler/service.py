import asyncio
import traceback
from datetime import datetime, timezone
from typing import Optional

from app.domains.scheduler import scheduled_jobs_repo
from app.domains.agents.registration_service import finalize_registry

POLL_SECONDS = 5

_task: Optional[asyncio.Task] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _poll_loop() -> None:
    while True:
        await asyncio.sleep(POLL_SECONDS)
        try:
            due = await scheduled_jobs_repo.list_due(_now_iso())
            for job in due:
                if job["kind"] == "finalize_registry":
                    await finalize_registry(job["entity_id"])
                await scheduled_jobs_repo.mark_done(job["id"])
        except Exception:
            print("[scheduler] poll failed")
            traceback.print_exc()


# Drains due `scheduled_jobs` rows (currently just fast-path auto-approval).
# Row-backed so a pending job still fires after a server restart — the bug the
# old client-only `window.setTimeout` had.
def start_scheduler() -> None:
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_poll_loop())
