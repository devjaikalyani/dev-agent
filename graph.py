"""
graph.py — LangGraph StateGraph definition.

Node topology:
  plan → explore → code → test ──(pass)──→ open_pr → END
                              └──(fail)──→ debug ──→ test (loop)
                              └──(max_retries)──→ END(failed)
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.planner import planner_node
from agent.explorer import explorer_node
from agent.coder import coder_node
from agent.tester import tester_node
from agent.debugger import debugger_node
from agent.pr_opener import pr_opener_node
import config


# ─────────────────────────────────────────────────────────────────────────────
# Conditional routing
# ─────────────────────────────────────────────────────────────────────────────

def route_after_test(state: AgentState) -> str:
    """
    Conditional edge from the 'test' node.

    Returns:
      "open_pr"  — all tests pass → create the pull request
      "debug"    — tests failed, retries remaining → fix and retry
      "failed"   — max retries exhausted → give up, surface error
    """
    if state["test_passed"]:
        return "open_pr"
    if state.get("retry_count", 0) >= config.MAX_RETRIES:
        return "failed"
    return "debug"


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the DevAgent LangGraph."""
    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("plan",     planner_node)
    g.add_node("explore",  explorer_node)
    g.add_node("code",     coder_node)
    g.add_node("test",     tester_node)
    g.add_node("debug",    debugger_node)
    g.add_node("open_pr",  pr_opener_node)

    # Entry point
    g.set_entry_point("plan")

    # Fixed edges
    g.add_edge("plan",    "explore")
    g.add_edge("explore", "code")
    g.add_edge("code",    "test")
    g.add_edge("debug",   "test")     # debug always re-runs tests
    g.add_edge("open_pr", END)

    # Conditional edge: test result decides next step
    g.add_conditional_edges(
        "test",
        route_after_test,
        {
            "open_pr": "open_pr",
            "debug":   "debug",
            "failed":  END,
        },
    )

    return g.compile()


# Singleton compiled graph — import this in main.py
app = build_graph()
