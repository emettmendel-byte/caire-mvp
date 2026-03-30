from typing import Any, Dict
from langgraph.graph import StateGraph, START, END
from .steps.nodes import (
    manual_repair_node,
    redteam_audit_node,
    repair_drafting_node,
    facts_extraction_node,
    symbols_predicates_node,
    factsheet_builder_node,
    tree_validation_node,
    governance_node
)
from ..models import GraphState

def build_workflow() -> StateGraph:
    workflow = StateGraph(GraphState)
    
    # ── Phase A: Audit & Repair ──
    workflow.add_node("manual_repair", manual_repair_node)
    workflow.add_node("redteam_audit", redteam_audit_node)
    workflow.add_node("repair_drafting", repair_drafting_node)
    
    # ── Phase B: Structuring ──
    workflow.add_node("facts_extraction", facts_extraction_node)
    workflow.add_node("symbols_predicates", symbols_predicates_node)
    workflow.add_node("factsheet_builder", factsheet_builder_node)
    
    # ── Phase D: Validation & Gov ──
    workflow.add_node("tree_validation", tree_validation_node)
    workflow.add_node("governance", governance_node)

    # ── Define Linear Flow ──
    workflow.add_edge(START, "manual_repair")
    workflow.add_edge("manual_repair", "redteam_audit")
    workflow.add_edge("redteam_audit", "repair_drafting")
    workflow.add_edge("repair_drafting", "facts_extraction")
    workflow.add_edge("facts_extraction", "symbols_predicates")
    workflow.add_edge("symbols_predicates", "factsheet_builder")
    workflow.add_edge("factsheet_builder", "tree_validation")
    workflow.add_edge("tree_validation", "governance")
    workflow.add_edge("governance", END)
    
    return workflow.compile()

# Global compiled graph instance
graph = build_workflow()
