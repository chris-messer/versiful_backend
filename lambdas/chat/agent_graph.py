"""
LangGraph companion graph (replaces the single LangChain chain).

Graph shape (spec §3 diagram, build plan F9):

    START
      -> guardrails
           |-- (crisis) --> END           # answer immediately, skip memory + LLM
           '-- (ok) ------> load_history
      load_history -> retrieve_memory -> generate -> extract -> persist -> END

The node bodies live as `step_*` methods on AgentService (single source of truth), so
the same pipeline can run with or without LangGraph installed. This module is a thin
orchestrator that wires those steps into a StateGraph.

- load_history   : normalize/truncate the DynamoDB episodic history the chat handler
                   already loaded (DynamoDB stays the system of record; we deliberately
                   do NOT use the LangGraph Postgres checkpointer — spec §5).
- retrieve_memory: assemble the Neon-backed companion context (structured-primary,
                   vector-secondary). Degrades to "" if Neon is unavailable.
- generate       : LLM + tools (get_versiful_info, recall) with PostHog tracing.
- extract        : post-turn GPT-4o-mini extraction (inline when state.extract_inline).
- persist        : write extracted memories/reflections to Neon (best-effort).

GRACEFUL DEGRADATION: only `generate` is on the critical path. `retrieve_memory`,
`extract`, and `persist` each swallow all errors, so any Neon/embedding problem just
means "no long-term recall this turn" — the core verse/chat reply still goes out.
"""
import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

logger = logging.getLogger()


class CompanionState(TypedDict, total=False):
    # request
    thread_id: str
    message: str
    channel: str
    user_id: Optional[str]
    bible_version: Optional[str]
    first_name: Optional[str]
    phone_number: Optional[str]
    session_id: Optional[str]
    posthog_distinct_id: Optional[str]
    trace_id: Optional[str]
    source_msg_id: Optional[str]
    history: List[Dict[str, str]]
    extract_inline: bool
    # derived
    needs_crisis: bool
    is_off_topic: bool
    memory_context: str
    response: str
    extraction: Optional[Dict[str, Any]]


def build_companion_graph(agent):
    """Compile the companion StateGraph, delegating each node to an AgentService step."""
    g = StateGraph(CompanionState)
    g.add_node("guardrails", agent.step_guardrails)
    g.add_node("load_history", agent.step_load_history)
    g.add_node("retrieve_memory", agent.step_retrieve_memory)
    g.add_node("generate", agent.step_generate)
    g.add_node("extract", agent.step_extract)
    g.add_node("persist", agent.step_persist)

    g.add_edge(START, "guardrails")
    g.add_conditional_edges(
        "guardrails", agent.route_after_guardrails,
        {"crisis": END, "continue": "load_history"},
    )
    g.add_edge("load_history", "retrieve_memory")
    g.add_edge("retrieve_memory", "generate")
    g.add_edge("generate", "extract")
    g.add_edge("extract", "persist")
    g.add_edge("persist", END)

    return g.compile()
