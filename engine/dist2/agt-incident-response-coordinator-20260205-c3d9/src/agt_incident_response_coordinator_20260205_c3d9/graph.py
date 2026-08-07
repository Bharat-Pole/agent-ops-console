"""Incident Response Coordinator — COORDINATOR + sub-agents (hand-written supervisor).

Topology: supervisor. A supervisor node routes to one ReAct sub-agent at a time
via Command(goto=…); each sub-agent returns control to the supervisor.
"""
from typing import Literal

from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from .model import build_model, has_credentials
from .memory import build_checkpointer
from .prompts import SYSTEM_PROMPT, SUBAGENT_PROMPTS
from .tools import ADVISORY_TOOLS

SUBAGENTS = ["log_analyzer", "impact_assessor", "comms_drafter", "notification_router"]

# advisory tools available to each sub-agent (<=3, read-only)
SUBAGENT_TOOLS = {
    "log_analyzer": ["log_reader", "incident_reader"],
    "impact_assessor": ["health_checker"],
    "comms_drafter": [],
    "notification_router": ["jira_reader"],
}

_TOOLS_BY_NAME = {getattr(t, "name", getattr(t, "__name__", "")): t for t in ADVISORY_TOOLS}


class _Route(BaseModel):
    """Which sub-agent should act next, or FINISH when the task is complete."""
    next: Literal["log_analyzer", "impact_assessor", "comms_drafter", "notification_router", "FINISH"]


def _subagent_tools(name):
    return [_TOOLS_BY_NAME[t] for t in SUBAGENT_TOOLS.get(name, []) if t in _TOOLS_BY_NAME]


def build_graph(model=None, checkpointer=None):
    model = model if model is not None else build_model()

    # one ReAct sub-graph per sub-agent (tool-less sub-agents get tools=[])
    workers = {
        name: create_react_agent(model, tools=_subagent_tools(name),
                                 prompt=SUBAGENT_PROMPTS.get(name, ""))
        for name in SUBAGENTS
    }

    def supervisor(state: MessagesState) -> Command[Literal["log_analyzer", "impact_assessor", "comms_drafter", "notification_router", "__end__"]]:
        decision = model.with_structured_output(_Route).invoke(
            [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        )
        nxt = getattr(decision, "next", "FINISH")
        return Command(goto=END if nxt == "FINISH" else nxt)

    g = StateGraph(MessagesState)
    g.add_node("supervisor", supervisor)
    for _name in SUBAGENTS:
        def _node(state, _w=workers[_name]):
            out = _w.invoke(state)
            return Command(goto="supervisor", update={"messages": out["messages"][-1:]})
        g.add_node(_name, _node)
    g.add_edge(START, "supervisor")

    return g.compile(
        checkpointer=checkpointer if checkpointer is not None else build_checkpointer(),
        interrupt_before=["notification_router"],
    )


graph = build_graph() if has_credentials() else None
