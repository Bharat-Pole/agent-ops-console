"""Warm the in-memory index from the bundled sample docs (embeds them once).

  python -m agt_incident_response_coordinator_20260205_c3d9.rag.ingest

The default store is in-memory (rebuilt per process). For persistence, swap
retriever.py for Chroma or AlloyDB/pgvector.
"""
from .retriever import _store, _load_docs


def main():
    n = len(_load_docs())
    _store()  # builds + embeds the in-memory index
    print(f"indexed {n} document(s) into the in-memory store")


if __name__ == "__main__":
    main()
