"""FastAPI server:  uvicorn agt_incident_response_coordinator_20260205_c3d9.runtime.server:app --reload

  GET  /health
  POST /converse   {"message": "...", "thread_id": "default"}
"""
from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from ..graph import build_graph

app = FastAPI(title="Incident Response Coordinator")
_graph = None


def _g():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


class Turn(BaseModel):
    message: str
    thread_id: str = "default"


@app.get("/health")
def health():
    return {"status": "ok", "agent": "agt-incident-response-coordinator-20260205-c3d9", "topology": "supervisor"}


@app.post("/converse")
def converse(turn: Turn):
    config = {"configurable": {"thread_id": turn.thread_id}}
    result = _g().invoke({"messages": [HumanMessage(content=turn.message)]}, config)
    return {"reply": result["messages"][-1].content}
