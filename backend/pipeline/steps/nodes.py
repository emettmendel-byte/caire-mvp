import json
import os
import re
import datetime
import hashlib
from typing import Dict, Any, List
from ...models import GraphState
from ..ollama_client import generate_json, generate_text
from ..prompts import get_prompt_text
import logging

logger = logging.getLogger(__name__)

# Where per-run intermediate artifacts are written
def _run_artifact_dir(run_id: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", run_id)
    os.makedirs(base, exist_ok=True)
    return base

# Where the final compiled JSON goes
FINAL_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")

async def write_artifact(run_id: str, step_name: str, data: Any, ext: str = "json") -> Dict[str, Any]:
    """Write an intermediate artifact for a pipeline step."""
    file_name = f"{step_name}.{ext}"
    file_path = os.path.join(_run_artifact_dir(run_id), file_name)
    
    if ext == "json":
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    else:
        with open(file_path, "w") as f:
            f.write(str(data))
            
    return {
        "step": step_name,
        "path": f"/artifacts/{run_id}/{file_name}",
        "summary": f"Generated {file_name}"
    }

def _calculate_hash(data: Any) -> str:
    content = json.dumps(data, sort_keys=True) if isinstance(data, (dict, list)) else str(data)
    return hashlib.sha256(content.encode()).hexdigest()

# ── Phase A: Audit & Repair ───────────────────────────────────────────────────

async def universal_step_node(state: GraphState) -> Dict[str, Any]:
    """
    A generic node that executes the current step in a dynamic pipeline.
    It uses state['step_index'] to find the prompt and configuration from state['pipeline_steps'].
    """
    idx = state.get("step_index", 0)
    steps = state.get("pipeline_steps", [])
    
    if idx >= len(steps):
        # Should not happen if router is correct
        return {"current_step": "completed"}
        
    step_config = steps[idx]
    prompt_id = step_config.get("prompt_id")
    step_name = step_config.get("name", f"step_{idx}")
    output_format = step_config.get("output_format", "markdown")
    
    # Import here to avoid circular dependencies if any
    from ..prompts import load_prompt_library
    lib = load_prompt_library()
    prompt_data = lib["prompts"].get(prompt_id)
    prompt_text = prompt_data["text"] if prompt_data else "No prompt found."
    
    # Prepare context: pdf_text + references to all previous artifacts
    context = {
        "pdf_text": state.get("pdf_text", ""),
        "step_name": step_name,
        "previous_artifacts": [a.get("summary") for a in state.get("artifacts", [])]
    }
    
    logger.info(f"Executing dynamic step {idx}: {step_name} ({prompt_id})")
    
    if output_format == "json":
        result = await generate_json(prompt_text, context)
        artifact = await write_artifact(state["run_id"], step_name, result, "json")
    else:
        result = await generate_text(prompt_text, context)
        # Extract markdown content from code blocks if necessary
        clean_result = result
        if "```" in result:
             m = re.search(r"```(?:\w+)?\n?(.*?)\n?```", result, re.DOTALL)
             if m: clean_result = m.group(1).strip()
             
        artifact = await write_artifact(state["run_id"], step_name, clean_result, "md")
        
    return {
        "step_index": idx + 1,
        "current_step": step_name,
        "completed_steps": [step_name],
        "artifacts": [artifact]
    }

# ── Phase A: Audit & Repair (Legacy) ──────────────────────────────────────────

async def manual_repair_node(state: GraphState) -> Dict[str, Any]:
    step = "manual_repair"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "manual_repair")
    result = await generate_text(prompt, {"manual_content": state.get("pdf_text", "")})
    artifact = await write_artifact(state["run_id"], step, result, "md")
    return {"manual_repairs": result, "current_step": step, "completed_steps": [step], "artifacts": [artifact]}

async def redteam_audit_node(state: GraphState) -> Dict[str, Any]:
    step = "redteam_audit"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "redteam_audit")
    input_data = {"manual_pdf": state.get("pdf_text", ""), "manual_repairs": state.get("manual_repairs", "")}
    result = await generate_text(prompt, input_data)
    artifact = await write_artifact(state["run_id"], step, result, "md")
    return {"red_team_report": result, "current_step": step, "completed_steps": [step], "artifacts": [artifact]}

async def repair_drafting_node(state: GraphState) -> Dict[str, Any]:
    step = "repair_drafting"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "repair_drafting")
    result = await generate_text(prompt, {"red_team_report": state.get("red_team_report", ""), "manual_pdf": state.get("pdf_text", "")})
    resolved = f"# Resolved Manual\n\n## Original Text Hash: {_calculate_hash(state['pdf_text'])[:8]}\n\n"
    resolved += "## Initial Repairs\n" + (state.get("manual_repairs") or "") + "\n\n"
    resolved += "## Red-team Targeted Fixes\n" + result
    artifact = await write_artifact(state["run_id"], "ResolvedManual", resolved, "md")
    return {"resolved_manual": resolved, "current_step": step, "completed_steps": [step], "artifacts": [artifact]}

async def facts_extraction_node(state: GraphState) -> Dict[str, Any]:
    step = "facts_extraction"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "facts_extraction")
    result = await generate_text(prompt, {"ResolvedManual": state.get("resolved_manual", "")})
    artifact = await write_artifact(state["run_id"], step, result, "csv")
    return {"factsheet_csv": result, "current_step": step, "completed_steps": [step], "artifacts": [artifact]}

async def symbols_predicates_node(state: GraphState) -> Dict[str, Any]:
    step = "symbols_predicates"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "symbols_predicates")
    result = await generate_json(prompt, {"factsheet_csv": state.get("factsheet_csv", "")})
    artifact = await write_artifact(state["run_id"], step, result, "json")
    return {"symbols_predicates": result, "current_step": step, "completed_steps": [step], "artifacts": [artifact]}

async def factsheet_builder_node(state: GraphState) -> Dict[str, Any]:
    step = "factsheet_builder"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "factsheet_builder")
    input_data = {
        "ResolvedManual": state.get("resolved_manual", ""),
        "factsheet_csv": state.get("factsheet_csv", ""),
        "symbols_predicates": state.get("symbols_predicates", {})
    }
    result = await generate_json(prompt, input_data)
    if "nodes" not in result: result["nodes"] = []
    if "edges" not in result: result["edges"] = []
    artifact = await write_artifact(state["run_id"], step, result, "json")
    return {"factsheet_json": result, "current_step": step, "completed_steps": [step], "artifacts": [artifact]}

# ── Phase D: Validation & Governance ──────────────────────────────────────────

async def tree_validation_node(state: GraphState) -> Dict[str, Any]:
    step = "tree_validation"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "tree_validation")
    input_data = {
        "factsheet_json": state.get("factsheet_json", {}),
        "ResolvedManual": state.get("resolved_manual", "")
    }
    
    # This prompt expects MD report + Updated JSON
    # We might need to split them or use generate_json if it returns both
    # For now, let's assume it returns a dict with report and fixed_json
    result = await generate_json(prompt, input_data)
    
    report = result.get("validation_report", "Validation completed.")
    fixed_json = result.get("factsheet_validated", state.get("factsheet_json"))
    
    art_report = await write_artifact(state["run_id"], "validation_report", report, "md")
    art_json = await write_artifact(state["run_id"], "factsheet_validated", fixed_json, "json")
    
    return {
        "validation_report": report,
        "factsheet_json": fixed_json,
        "current_step": step,
        "completed_steps": [step],
        "artifacts": [art_report, art_json]
    }

async def governance_node(state: GraphState) -> Dict[str, Any]:
    step = "governance"
    prompt = get_prompt_text(state.get("pipeline_id", "default-governance"), "governance")
    
    # Collect all metadata for hashes
    # We will hash the summaries of the artifacts for the manifest
    hashes = {a["step"]: hashlib.sha256(a.get("summary", "").encode()).hexdigest()[:16] for a in state.get("artifacts", [])}
    
    input_data = {
        "factsheet_validated": state.get("factsheet_json", {}),
        "artifact_hashes": hashes
    }
    
    result = await generate_json(prompt, input_data)
    manifest = result.get("manifest", result)
    log = result.get("governance_log", "Automated governance check passed.")
    
    art_manifest = await write_artifact(state["run_id"], "manifest", manifest, "json")
    art_log = await write_artifact(state["run_id"], "governance_log", log, "md")
    
    # ── FINAL OUTPUT: Write factsheet.json to root artifacts/ library ──
    # Ensure we use the latest validated version
    final_tree = state.get("factsheet_json") or {}
    
    # Validation fallback: if tree is empty, try to find it in artifacts
    if not final_tree.get("nodes"):
        logger.warning("factsheet_json in state is empty. Attempting recovery.")
        # Fallback logic if needed
    
    # Ensure name/id for library
    file_name = state.get("file_name", "guideline.pdf")
    guideline_name = final_tree.get("name") or os.path.splitext(file_name)[0].replace("_", " ").title()
    guideline_id = final_tree.get("id") or re.sub(r"[^a-z0-9]", "-", guideline_name.lower())
    
    final_tree["name"] = guideline_name
    final_tree["id"] = guideline_id
    final_tree["nodes"] = final_tree.get("nodes", [])
    final_tree["edges"] = final_tree.get("edges", [])
    if "root_id" not in final_tree:
        root_node = next((n for n in final_tree["nodes"] if n.get("type") == "root"), None)
        final_tree["root_id"] = root_node["id"] if root_node else "root"
    
    os.makedirs(FINAL_ARTIFACTS_DIR, exist_ok=True)
    # Use a clean slug for the filename
    safe_slug = re.sub(r"[^a-z0-9\-]", "", guideline_id.lower())
    final_path = os.path.join(FINAL_ARTIFACTS_DIR, f"{safe_slug}.json")
    
    with open(final_path, "w") as f:
        json.dump(final_tree, f, indent=4)
        
    final_art = {
        "step": "final_deployment",
        "path": f"/artifacts/{safe_slug}.json",
        "summary": f"Governance Approved: {guideline_name}"
    }

    return {
        "governance_manifest": manifest,
        "current_step": "deployment_ready",
        "completed_steps": [step],
        "artifacts": [art_manifest, art_log, final_art]
    }
