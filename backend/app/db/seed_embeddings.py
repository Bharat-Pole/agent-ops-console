from app.repositories import knowledge_chunks_repo
from app.seed_data.snapshot import load_seed_snapshot
from app.services.embeddings import embed_batch, is_embeddings_configured


async def seed_embeddings_if_empty() -> None:
    if await knowledge_chunks_repo.count() > 0:
        return

    if not is_embeddings_configured():
        print(
            "[seed] OPENAI_API_KEY not set — skipping knowledge_chunks embedding seed. "
            "RAG-enabled agents get ungrounded answers until this is set and the server restarted."
        )
        return

    snapshot = load_seed_snapshot()
    items = [
        {"id": f"{s['id']}:{sn['doc_id']}", "source_id": s["id"], "doc_id": sn["doc_id"], "text": sn["text"]}
        for s in snapshot["sources"]
        for sn in s["snippets"]
    ]
    vectors = await embed_batch([i["text"] for i in items])
    for item, vector in zip(items, vectors):
        await knowledge_chunks_repo.insert({**item, "embedding": vector})

    print(f"[seed] embedded {len(items)} snippets across {len(snapshot['sources'])} sources")
