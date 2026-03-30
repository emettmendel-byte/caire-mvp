from typing import Any, Dict, Literal
from langgraph.graph import StateGraph, START, END
from .steps.nodes import universal_step_node
from ..models import GraphState

def should_continue(state: GraphState) -> Literal["continue", "end"]:
    """
    Router function to decide whether to continue the pipeline or end.
    """
    idx = state.get("step_index", 0)
    steps = state.get("pipeline_steps", [])
    
    if idx < len(steps):
        return "continue"
    return "end"

def build_dynamic_workflow() -> StateGraph:
    workflow = StateGraph(GraphState)
    
    # ── Single Universal Node ──
    # This node executes any prompt based on the current step_index
    workflow.add_node("execute_step", universal_step_node)
    
    # ── Define Looping Flow ──
    workflow.add_edge(START, "execute_step")
    
    # Conditional edge to loop or end
    workflow.add_conditional_edges(
        "execute_step",
        should_continue,
        {
            "continue": "execute_step",
            "end": END
        }
    )
    
    return workflow.compile()

# Dynamic workflow instance
dynamic_graph = build_dynamic_workflow()
