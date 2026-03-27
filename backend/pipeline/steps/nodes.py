import json
import os
import re
import datetime
from typing import Dict, Any, List
from ...models import GraphState
from ..ollama_client import generate_json
from ..prompts import get_prompt_text
import logging

logger = logging.getLogger(__name__)

# Where per-run intermediate artifacts are written
def _run_artifact_dir(run_id: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", run_id)
    os.makedirs(base, exist_ok=True)
    return base

# Where the final compiled JSON goes (picked up by /api/library)
FINAL_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")


async def write_artifact(run_id: str, step_name: str, data: Any) -> Dict[str, Any]:
    """Write an intermediate artifact for a pipeline step."""
    file_path = os.path.join(_run_artifact_dir(run_id), f"{step_name}.json")
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
    return {
        "step": step_name,
        "path": f"/artifacts/{run_id}/{step_name}.json",
        "summary": f"Completed {step_name}"
    }


def _extract_nodes_edges(result: Any) -> Dict[str, Any]:
    """
    Normalise whatever the LLM returns into {nodes: [...], edges: [...]}.
    Handles result being a dict with nodes/edges, or a list, or fallback to empty.
    """
    if isinstance(result, dict):
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
    elif isinstance(result, list):
        # Maybe the LLM returned a flat list of nodes
        nodes = result
        edges = []
    else:
        nodes = []
        edges = []
    return {"nodes": nodes if isinstance(nodes, list) else [], 
            "edges": edges if isinstance(edges, list) else []}


def _slug(name: str) -> str:
    """Turn a guideline name into a kebab-case id slug."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "guideline"


# ── Step 1: Extract text ──────────────────────────────────────────────────────

async def extract_text_node(state: GraphState) -> Dict[str, Any]:
    step = "extract_text"
    prompt = get_prompt_text("prompt_1")
    result = await generate_json(prompt, {"pdf_text": state.get("pdf_text", "")})
    artifact = await write_artifact(state["run_id"], step, result)
    return {
        "extracted_data": result,
        "current_step": step,
        "completed_steps": [step],
        "artifacts": [artifact]
    }


# ── Step 2: Chunking ──────────────────────────────────────────────────────────

async def chunking_node(state: GraphState) -> Dict[str, Any]:
    step = "chunking"
    prompt = get_prompt_text("prompt_2")
    result = await generate_json(prompt, state.get("extracted_data", {}))
    artifact = await write_artifact(state["run_id"], step, result)
    return {
        "chunks": result,
        "current_step": step,
        "completed_steps": [step],
        "artifacts": [artifact],
        "current_chunk_index": 0,
        "chunk_decisions": [],
        "chunk_subtrees": []
    }


# ── Step 3: Decision identifier (per chunk) ───────────────────────────────────

async def decision_identifier_node(state: GraphState) -> Dict[str, Any]:
    step = "decision_identification"
    prompt = get_prompt_text("prompt_3")
    idx = state.get("current_chunk_index", 0)

    chunks_container = state.get("chunks", {})
    chunk_list = (
        chunks_container.get("chunks", [])
        if isinstance(chunks_container, dict)
        else chunks_container
    )

    if not chunk_list or idx >= len(chunk_list):
        return {"current_step": step}

    current_chunk = chunk_list[idx]
    result = await generate_json(prompt, current_chunk)
    # Normalise to {nodes, edges}
    fragment = _extract_nodes_edges(result)

    artifact = await write_artifact(state["run_id"], f"{step}_chunk_{idx}", fragment)

    new_decisions = list(state.get("chunk_decisions", []))
    new_decisions.append(fragment)

    return {
        "chunk_decisions": new_decisions,
        "current_step": f"{step} ({idx+1}/{len(chunk_list)})",
    }


# ── Step 3.5: Subtree builder (per chunk) ─────────────────────────────────────

async def subtree_builder_node(state: GraphState) -> Dict[str, Any]:
    step = "subtree_building"
    prompt = get_prompt_text("prompt_3_5")
    idx = state.get("current_chunk_index", 0)

    chunks_container = state.get("chunks", {})
    chunk_list = (
        chunks_container.get("chunks", [])
        if isinstance(chunks_container, dict)
        else chunks_container
    )

    if not chunk_list or idx >= len(chunk_list):
        return {"current_step": step}

    current_chunk = chunk_list[idx]
    decisions = state.get("chunk_decisions", [])
    current_decision = decisions[-1] if decisions else {"nodes": [], "edges": []}

    input_payload = {
        "chunk": current_chunk,
        "decisions": current_decision
    }

    result = await generate_json(prompt, input_payload)
    fragment = _extract_nodes_edges(result)

    artifact = await write_artifact(state["run_id"], f"{step}_chunk_{idx}", fragment)

    new_subtrees = list(state.get("chunk_subtrees", []))
    new_subtrees.append(fragment)

    return {
        "chunk_subtrees": new_subtrees,
        "current_step": f"{step} ({idx+1}/{len(chunk_list)})",
        "current_chunk_index": idx + 1
    }


# ── Step 4: Tree merger ───────────────────────────────────────────────────────

async def tree_merger_node(state: GraphState) -> Dict[str, Any]:
    step = "tree_building"
    prompt = get_prompt_text("prompt_4")

    subtrees = state.get("chunk_subtrees", [])
    await write_artifact(state["run_id"], "all_chunk_subtrees", subtrees)

    result = await generate_json(prompt, subtrees)
    merged = _extract_nodes_edges(result)

    artifact = await write_artifact(state["run_id"], step, merged)
    return {
        "tree_draft": merged,
        "current_step": step,
        "completed_steps": ["decision_identification", "subtree_building", step],
        "artifacts": [artifact]
    }


# ── Step 5: Validator ─────────────────────────────────────────────────────────

async def validator_node(state: GraphState) -> Dict[str, Any]:
    step = "validation"
    prompt = get_prompt_text("prompt_5")

    tree_draft = state.get("tree_draft", {"nodes": [], "edges": []})
    input_data = {
        "nodes": tree_draft.get("nodes", []),
        "edges": tree_draft.get("edges", []),
        "decisions": state.get("chunk_decisions", [])
    }

    result = await generate_json(prompt, input_data)

    artifact = await write_artifact(
        state["run_id"],
        f"{step}_attempt_{state.get('validation_retries', 0)}",
        result
    )
    return {
        "validation_status": result,
        "current_step": step,
        "completed_steps": [step],
        "artifacts": [artifact]
    }


# ── Step 6: JSON Compiler (writes to top-level artifacts/) ────────────────────

async def json_compiler_node(state: GraphState) -> Dict[str, Any]:
    step = "json_compilation"
    prompt = get_prompt_text("prompt_6")

    # Pull the best available nodes/edges: prefer validator output, fall back to merger
    validation = state.get("validation_status", {})
    tree_draft = state.get("tree_draft", {"nodes": [], "edges": []})

    nodes = (
        validation.get("nodes")
        or tree_draft.get("nodes", [])
    )
    edges = (
        validation.get("edges")
        or tree_draft.get("edges", [])
    )

    file_name = state.get("file_name", "guideline.pdf")

    input_data = {
        "file_name": file_name,
        "nodes": nodes,
        "edges": edges,
        "validation_summary": {
            "valid": validation.get("valid", True),
            "issues": validation.get("issues", [])
        }
    }

    result = await generate_json(prompt, input_data)

    # ── Ensure the result is a well-formed CAIRE document ─────────────────────
    # If the LLM wrapped things, unwrap them
    if isinstance(result, dict) and "tree" in result and "nodes" not in result:
        inner = result.get("tree", {})
        result = {
            "nodes": inner.get("nodes", nodes),
            "edges": inner.get("edges", edges),
        }

    # Guarantee required top-level fields exist
    if not isinstance(result, dict):
        result = {}

    if "nodes" not in result or not result["nodes"]:
        result["nodes"] = nodes
    if "edges" not in result or not result["edges"]:
        result["edges"] = edges

    # Derive id / name from the file if the LLM omitted them
    guideline_name = result.get("name") or os.path.splitext(file_name)[0].replace("_", " ").replace("-", " ").title()
    guideline_id = result.get("id") or _slug(guideline_name)

    # Find root node id
    root_node = next(
        (n for n in result.get("nodes", []) if isinstance(n, dict) and n.get("type") == "root"),
        None
    )
    root_id = result.get("root_id") or (root_node["id"] if root_node else "root")

    final_doc = {
        "id": guideline_id,
        "version": result.get("version", "1.0.0"),
        "name": guideline_name,
        "description": result.get("description", f"Clinical decision tree extracted from {file_name}"),
        "root_id": root_id,
        "nodes": result["nodes"],
        "edges": result["edges"],
    }

    # ── Write intermediate artifact (per-run folder) ──────────────────────────
    await write_artifact(state["run_id"], step, final_doc)

    # ── Write final artifact to top-level artifacts/ (for /api/library) ───────
    os.makedirs(FINAL_ARTIFACTS_DIR, exist_ok=True)
    safe_name = re.sub(r"[^a-z0-9\-]", "", guideline_id)[:80] or state["run_id"]
    final_path = os.path.join(FINAL_ARTIFACTS_DIR, f"{safe_name}.json")

    # Avoid name collision by appending run_id prefix when the file already exists
    if os.path.exists(final_path):
        final_path = os.path.join(FINAL_ARTIFACTS_DIR, f"{safe_name}-{state['run_id'][:8]}.json")

    with open(final_path, "w") as f:
        json.dump(final_doc, f, indent=4)

    artifact = {
        "step": step,
        "path": f"/artifacts/{os.path.basename(final_path)}",
        "summary": f"Compiled {guideline_name}"
    }

    return {
        "final_json": final_doc,
        "current_step": step,
        "completed_steps": [step],
        "artifacts": [artifact]
    }
