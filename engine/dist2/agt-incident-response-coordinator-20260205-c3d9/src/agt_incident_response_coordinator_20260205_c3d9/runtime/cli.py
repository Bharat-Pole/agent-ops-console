"""CLI runner:  python -m agt_incident_response_coordinator_20260205_c3d9.runtime.cli "your question" """
import sys

from langchain_core.messages import HumanMessage

from ..graph import build_graph


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    question = " ".join(argv).strip() or "Hello"
    graph = build_graph()
    config = {"configurable": {"thread_id": "cli"}}
    result = graph.invoke({"messages": [HumanMessage(content=question)]}, config)
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
