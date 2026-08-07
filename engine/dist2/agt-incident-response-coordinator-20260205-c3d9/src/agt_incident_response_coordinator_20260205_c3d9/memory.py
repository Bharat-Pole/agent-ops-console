"""Checkpointer factory. Local in-memory by default — swap for a persistent
checkpointer (e.g. langgraph-checkpoint-postgres / -sqlite) in production."""
from langgraph.checkpoint.memory import MemorySaver


def build_checkpointer():
    return MemorySaver()
