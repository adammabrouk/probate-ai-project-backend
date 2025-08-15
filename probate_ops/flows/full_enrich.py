from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from ..core.registry import registry


class State(TypedDict):
    records: List[dict]
    i: int


def score_node(state: State):
    i = state["i"]
    rec = state["records"][i]
    verdict = registry.call("score_llm", record=rec)
    rec.update(verdict)
    state["i"] = i + 1
    return state


def build_graph():
    g = StateGraph(State)
    g.add_node("score_one", score_node)
    g.set_entry_point("score_one")
    g.add_conditional_edges(
        "score_one",
        lambda s: END if s["i"] >= len(s["records"]) else "score_one",
    )
    return g.compile()
