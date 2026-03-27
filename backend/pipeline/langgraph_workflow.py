from typing import Any, Dict
from langgraph.graph import StateGraph, START, END
from .steps.nodes import (
    extract_text_node,
    chunking_node,
    decision_identifier_node,
    subtree_builder_node,
    tree_merger_node,
    validator_node,
    json_compiler_node
)
from ..models import GraphState

def should_loop_next_chunk(state: GraphState):
    """
    Checks if there are more chunks to process.
    """
    idx = state.get("current_chunk_index", 0)
    
    chunks_container = state.get("chunks", {})
    if isinstance(chunks_container, dict):
        chunk_list = chunks_container.get("chunks", [])
    elif isinstance(chunks_container, list):
        chunk_list = chunks_container
    else:
        chunk_list = []
        
    if idx < len(chunk_list):
        return "decision_identification"
    else:
        return "tree_merging"

def should_compile(state: GraphState):
    """
    Conditional logic after validation.
    """
    retries = state.get("validation_retries", 0)
    is_valid = False
    if state.get("validation_status") and isinstance(state["validation_status"], dict):
        is_valid = state["validation_status"].get("valid", False) or state["validation_status"].get("is_valid", False)
        
    if is_valid or retries >= 3:
        return "json_compilation"
    else:
        return "increment_retry"

def increment_retry_node(state: GraphState) -> Dict[str, Any]:
    return {"validation_retries": state.get("validation_retries", 0) + 1}

def build_workflow() -> StateGraph:
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("extract_text", extract_text_node)
    workflow.add_node("chunking", chunking_node)
    
    # Loop Nodes
    workflow.add_node("decision_identification", decision_identifier_node)
    workflow.add_node("subtree_building", subtree_builder_node)
    
    # Assembly Nodes
    workflow.add_node("tree_merging", tree_merger_node)
    workflow.add_node("validation", validator_node)
    workflow.add_node("json_compilation", json_compiler_node)
    workflow.add_node("increment_retry", increment_retry_node)

    # Add edges
    workflow.add_edge(START, "extract_text")
    workflow.add_edge("extract_text", "chunking")
    workflow.add_edge("chunking", "decision_identification")
    
    workflow.add_edge("decision_identification", "subtree_building")
    
    # Conditional Loop logic: if we have more chunks, loop back to decision_identification.
    workflow.add_conditional_edges(
        "subtree_building",
        should_loop_next_chunk,
        {
            "decision_identification": "decision_identification",
            "tree_merging": "tree_merging"
        }
    )
    
    workflow.add_edge("tree_merging", "validation")
    
    # Conditional edge after validation
    workflow.add_conditional_edges(
        "validation",
        should_compile,
        {
            "json_compilation": "json_compilation",
            "increment_retry": "increment_retry"
        }
    )
    
    # From increment retry, go back to tree merging
    workflow.add_edge("increment_retry", "tree_merging")
    
    # Compile edge
    workflow.add_edge("json_compilation", END)
    
    return workflow.compile()

# Global compiled graph instance
graph = build_workflow()
