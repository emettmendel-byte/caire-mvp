import json
import os
import re
import datetime
import hashlib
import time
from typing import Dict, Any, List, Optional
from ...models import GraphState
from ..ollama_client import generate_json, generate_text
from ..prompts import get_prompt_text
import logging

logger = logging.getLogger(__name__)
DEBUG_LOG_PATH = "/Users/emett/Desktop/caire-mvp/.cursor/debug-a7d7a6.log"
DEBUG_SESSION_ID = "a7d7a6"

def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
    payload = {
        "sessionId": DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass

# Where per-run intermediate artifacts are written
def _run_artifact_dir(run_id: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", run_id)
    # Create per-run directory and, if newly created, write a small metadata file
    # so it is easy to inspect when the run was produced.
    if not os.path.isdir(base):
        os.makedirs(base, exist_ok=True)
        meta_path = os.path.join(base, "_run_meta.json")
        try:
            now = datetime.datetime.utcnow()
            meta = {
                "run_id": run_id,
                "created_at": now.isoformat() + "Z",
                "created_at_unix": int(now.timestamp()),
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=4)
        except Exception:
            # Metadata is best-effort; failures here should not break the pipeline.
            logger.warning("Failed to write _run_meta.json for run_id=%s", run_id)
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

def _collect_section_texts(sections: Any) -> List[str]:
    """Flatten nested section/subsection content blocks into plain text snippets."""
    out: List[str] = []
    if not isinstance(sections, list):
        return out
    for s in sections:
        if not isinstance(s, dict):
            continue
        title = str(s.get("title", "")).strip()
        content = str(s.get("content", "")).strip()
        if title:
            out.append(f"# {title}")
        if content:
            out.append(content)
        nested = s.get("subsections")
        if isinstance(nested, list):
            out.extend(_collect_section_texts(nested))
    return out

def _normalize_prompt1_output(result: Any, raw_pdf_text: str) -> Dict[str, Any]:
    """
    Normalize prompt_1 output into the shape prompt_2 expects:
    {full_text, headings, tables, decision_phrases}.
    """
    if not isinstance(result, dict):
        return {
            "full_text": raw_pdf_text or "",
            "headings": [],
            "tables": [],
            "decision_phrases": [],
        }

    if "full_text" in result and isinstance(result.get("full_text"), str):
        result.setdefault("headings", [])
        result.setdefault("tables", [])
        result.setdefault("decision_phrases", [])
        return result

    headings: List[str] = []
    sections = result.get("sections")
    if isinstance(sections, list):
        for s in sections:
            if isinstance(s, dict) and s.get("title"):
                headings.append(str(s.get("title")))

    joined = "\n\n".join(_collect_section_texts(sections)).strip()
    if not joined:
        joined = str(result.get("description", "")).strip() or raw_pdf_text or ""

    return {
        "full_text": joined,
        "headings": headings,
        "tables": result.get("tables", []) if isinstance(result.get("tables"), list) else [],
        "decision_phrases": result.get("decision_phrases", []) if isinstance(result.get("decision_phrases"), list) else [],
    }

def _build_fallback_chunks(full_text: str, headings: Any) -> Dict[str, Any]:
    """
    Deterministic fallback for prompt_2 when model returns instruction-like chunks.
    Keeps chain alive with real source text instead of prompt echo.
    """
    text = (full_text or "").strip()
    if not text:
        return {"chunks": []}
    parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: List[Dict[str, Any]] = []
    current = ""
    idx = 1
    for p in parts:
        if len(current) + len(p) + 2 <= 1200:
            current = f"{current}\n\n{p}".strip()
        else:
            chunks.append({
                "id": f"chunk_{idx}",
                "title": f"Chunk {idx}",
                "content": current,
                "type": "decision",
            })
            idx += 1
            current = p
    if current:
        chunks.append({
            "id": f"chunk_{idx}",
            "title": f"Chunk {idx}",
            "content": current,
            "type": "decision",
        })

    # Prefer heading labels when available.
    if isinstance(headings, list):
        for i, h in enumerate(headings):
            if i < len(chunks) and isinstance(h, str) and h.strip():
                chunks[i]["title"] = h.strip()
    return {"chunks": chunks}

def _chunks_look_instructional(chunks: Any) -> bool:
    if not isinstance(chunks, list) or not chunks:
        return True
    joined = " ".join(str(c.get("content", "")) for c in chunks if isinstance(c, dict)).lower()
    bad_markers = [
        "output only valid json",
        "payload below contains",
        "critical: output only",
        "json structure",
    ]
    return any(m in joined for m in bad_markers)

def _is_root_only_graph(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    nodes = result.get("nodes")
    edges = result.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return False
    if len(nodes) != 1 or len(edges) != 0:
        return False
    node0 = nodes[0] if nodes else {}
    return isinstance(node0, dict) and node0.get("type") == "root"

# ── Phase A: Audit & Repair ───────────────────────────────────────────────────

async def universal_step_node(state: GraphState) -> Dict[str, Any]:
    """
    A generic node that executes the current step in a dynamic pipeline.
    It uses state['step_index'] to find the prompt and configuration from state['pipeline_steps'].
    """
    def prompt_looks_like_json_only(prompt_text: str) -> bool:
        # Heuristic: many prompt templates include explicit "ONLY valid JSON" wording.
        p = (prompt_text or "").lower()
        markers = [
            "return only valid json",
            "output only valid json",
            "return only json",
            "output only json",
            "json schema",
            "only valid json",
            "must match exact schema",
        ]
        return any(m in p for m in markers)

    idx = state.get("step_index", 0)
    steps = state.get("pipeline_steps", [])
    run_id = state.get("run_id", "unknown")
    # region agent log
    _debug_log(
        run_id,
        "H1",
        "nodes.py:universal_step_node:entry",
        "Step entry",
        {"step_index": idx, "total_steps": len(steps), "pipeline_id": state.get("pipeline_id")},
    )
    # endregion
    
    if idx >= len(steps):
        # Should not happen if router is correct
        return {"current_step": "completed"}
        
    step_config = steps[idx]
    step_id = step_config.get("id", f"step_{idx}")
    step_name = step_config.get("name", step_id)

    prompt_text = step_config.get("prompt_text")
    prompt_id = step_config.get("prompt_id")
    
    # Import here to avoid circular dependencies if any
    from ..prompts import load_prompt_library
    lib = load_prompt_library()
    if not prompt_text and prompt_id:
        prompt_data = lib.get("prompts", {}).get(prompt_id)
        prompt_text = prompt_data["text"] if prompt_data else ""

    prompt_text = prompt_text or "No prompt found."

    output_format = step_config.get("output_format")
    if not output_format:
        output_format = "json" if prompt_looks_like_json_only(prompt_text) else "markdown"

    # -----------------------------
    # Special-case: sample prompt-chain wiring
    # -----------------------------
    # Your “sample chain” prompts are designed to run sequentially with structured
    # inputs between steps. The default runner only passes summaries, so for
    # these prompts we detect the stage and build the exact input payloads.
    sample_outputs: Dict[str, Any] = state.get("sample_outputs", {}) or {}

    def _detect_sample_stage(pid: str, ptxt: str) -> Optional[str]:
        # If the recipe stored an explicit prompt id, trust it.
        if pid in {"prompt_1", "prompt_2", "prompt_3", "prompt_3_5", "prompt_4", "prompt_5", "prompt_6"}:
            return pid
        # Otherwise detect by distinctive prompt text.
        t = (ptxt or "").lower()
        if "you are a pdf extractor" in t:
            return "prompt_1"
        if "segment the guideline into logical chunks focused on decisions" in t:
            return "prompt_2"
        if "clinical decision-point extractor" in t:
            return "prompt_3"
        if "consistent sub-graph fragment" in t or "subtree builder" in t:
            return "prompt_3_5"
        if "merge them into a single master decision tree" in t:
            return "prompt_4"
        if "validate it and fix any problems" in t:
            return "prompt_5"
        if "final step in a clinical guideline parsing pipeline" in t:
            return "prompt_6"
        return None

    sample_stage = _detect_sample_stage(prompt_id or "", prompt_text)

    if sample_stage is not None:
        output_format = "json"
    # region agent log
    _debug_log(
        run_id,
        "H2",
        "nodes.py:universal_step_node:stage-detect",
        "Stage and output mode resolved",
        {"step_id": step_id, "step_name": step_name, "prompt_id": prompt_id, "sample_stage": sample_stage, "output_format": output_format},
    )
    # endregion

    def _pick_best_chunk_from_prompt2() -> Dict[str, Any]:
        chunk_payload = sample_outputs.get("prompt_2", {})
        chunks = chunk_payload.get("chunks") if isinstance(chunk_payload, dict) else None
        if isinstance(chunks, list) and chunks:
            # Prefer chunks that likely contain decisions over generic intro content.
            best: Dict[str, Any] = {}
            best_score = -1
            for c in chunks:
                if not isinstance(c, dict):
                    continue
                score = 0
                ctype = str(c.get("type", "")).lower()
                if ctype == "decision":
                    score += 3
                if ctype == "criteria":
                    score += 2
                content = str(c.get("content", "")).lower()
                if any(k in content for k in [" if ", " then ", " should ", " must ", " when ", " recommend"]):
                    score += 2
                if len(content) > 180:
                    score += 1
                if score > best_score:
                    best_score = score
                    best = c
            if best:
                return best
            first = chunks[0]
            return first if isinstance(first, dict) else {}
        return {}

    sample_input_data: Any = None
    if sample_stage is not None and output_format == "json":
        # Provide exact input shapes that match the sample prompt “Input:” sections.
        if sample_stage == "prompt_1":
            sample_input_data = {"pdf_text": state.get("pdf_text", "")}
        elif sample_stage == "prompt_2":
            extract_out = sample_outputs.get("prompt_1", {}) if isinstance(sample_outputs, dict) else {}
            sample_input_data = {
                "full_text": extract_out.get("full_text", ""),
                "headings": extract_out.get("headings", []),
            }
        elif sample_stage == "prompt_3":
            chosen_chunk = _pick_best_chunk_from_prompt2()
            sample_input_data = chosen_chunk
            # region agent log
            _debug_log(
                run_id,
                "H6",
                "nodes.py:universal_step_node:prompt3-chunk-choice",
                "Selected chunk for prompt_3",
                {
                    "chunk_id": chosen_chunk.get("id") if isinstance(chosen_chunk, dict) else None,
                    "chunk_title": chosen_chunk.get("title") if isinstance(chosen_chunk, dict) else None,
                    "chunk_type": chosen_chunk.get("type") if isinstance(chosen_chunk, dict) else None,
                },
            )
            # endregion
        elif sample_stage == "prompt_3_5":
            chunk = _pick_best_chunk_from_prompt2()
            decisions_out = sample_outputs.get("prompt_3", {}) if isinstance(sample_outputs, dict) else {}
            sample_input_data = {"chunk": chunk, "decisions": decisions_out}
        elif sample_stage == "prompt_4":
            decisions_out = sample_outputs.get("prompt_3", {}) if isinstance(sample_outputs, dict) else {}
            subtree_out = sample_outputs.get("prompt_3_5", {}) if isinstance(sample_outputs, dict) else {}
            fragments: List[Dict[str, Any]] = []
            if isinstance(decisions_out, dict) and (decisions_out.get("nodes") or decisions_out.get("edges")):
                fragments.append(decisions_out)
            if isinstance(subtree_out, dict) and (subtree_out.get("nodes") or subtree_out.get("edges")):
                fragments.append(subtree_out)
            sample_input_data = fragments
            # region agent log
            _debug_log(
                run_id,
                "H6",
                "nodes.py:universal_step_node:prompt4-fragments",
                "Prepared fragments for prompt_4",
                {"fragment_count": len(fragments)},
            )
            # endregion
        elif sample_stage == "prompt_5":
            merge_out = sample_outputs.get("prompt_4", {}) if isinstance(sample_outputs, dict) else {}
            if isinstance(merge_out, dict):
                sample_input_data = {
                    "nodes": merge_out.get("nodes", []),
                    "edges": merge_out.get("edges", []),
                    "decisions": merge_out,
                }
            else:
                sample_input_data = {"nodes": [], "edges": [], "decisions": {}}
        elif sample_stage == "prompt_6":
            validation_out = sample_outputs.get("prompt_5", {}) if isinstance(sample_outputs, dict) else {}
            sample_input_data = {
                "file_name": state.get("file_name", "guideline.pdf"),
                "nodes": validation_out.get("nodes", []),
                "edges": validation_out.get("edges", []),
                "validation_summary": validation_out,
            }
    
    # Prepare context: pdf_text + references to all previous artifacts
    context = {
        "pdf_text": state.get("pdf_text", ""),
        "step_name": step_name,
        "previous_artifacts": [a.get("summary") for a in state.get("artifacts", [])]
    }
    
    logger.info(f"Executing dynamic step {idx}: {step_name} ({prompt_id})")
    
    if output_format == "json":
        json_input_data = sample_input_data if sample_input_data is not None else context
        # region agent log
        _debug_log(
            run_id,
            "H3",
            "nodes.py:universal_step_node:before-generate-json",
            "JSON generation input summary",
            {
                "step_id": step_id,
                "sample_stage": sample_stage,
                "input_keys": list(json_input_data.keys()) if isinstance(json_input_data, dict) else "non-dict",
                "input_nodes": len(json_input_data.get("nodes", [])) if isinstance(json_input_data, dict) and isinstance(json_input_data.get("nodes"), list) else None,
                "input_edges": len(json_input_data.get("edges", [])) if isinstance(json_input_data, dict) and isinstance(json_input_data.get("edges"), list) else None,
            },
        )
        # endregion
        result = await generate_json(prompt_text, json_input_data)

        # Sample pipeline hardening:
        # 1) normalize prompt_1 shape
        # 2) replace bad chunking outputs with deterministic chunking
        # 3) retry root-only graph outputs once for graph-building stages
        if sample_stage == "prompt_1":
            result = _normalize_prompt1_output(result, state.get("pdf_text", ""))
        elif sample_stage == "prompt_2":
            if not isinstance(result, dict):
                result = {"chunks": []}
            if _chunks_look_instructional(result.get("chunks")):
                # region agent log
                _debug_log(
                    run_id,
                    "H4",
                    "nodes.py:universal_step_node:prompt2-fallback",
                    "Prompt 2 output looked instructional, using fallback chunking",
                    {"step_id": step_id, "returned_chunk_count": len(result.get("chunks", [])) if isinstance(result, dict) and isinstance(result.get("chunks"), list) else 0},
                )
                # endregion
                src = sample_outputs.get("prompt_1", {})
                result = _build_fallback_chunks(
                    str(src.get("full_text", "")),
                    src.get("headings", []),
                )
        elif sample_stage in {"prompt_3", "prompt_3_5", "prompt_4", "prompt_5"} and _is_root_only_graph(result):
            # region agent log
            _debug_log(
                run_id,
                "H5",
                "nodes.py:universal_step_node:root-only-retry",
                "Root-only graph detected, retrying once",
                {"step_id": step_id, "sample_stage": sample_stage},
            )
            # endregion
            retry_prompt = (
                f"{prompt_text}\n\n"
                "RETRY REQUIREMENT: Your previous output collapsed to a root-only graph. "
                "Use the provided input content to produce a non-trivial graph with at least one "
                "question or outcome node and at least one edge when decision content exists. "
                "Do not echo instructions. Return only valid JSON."
            )
            retry_result = await generate_json(retry_prompt, json_input_data)
            if not _is_root_only_graph(retry_result):
                result = retry_result

        # If merger dropped edges but subtree builder had them, preserve connectivity.
        if sample_stage == "prompt_4" and isinstance(result, dict):
            if "edges" not in result or not isinstance(result.get("edges"), list):
                subtree_out = sample_outputs.get("prompt_3_5", {}) if isinstance(sample_outputs, dict) else {}
                if isinstance(subtree_out, dict) and isinstance(subtree_out.get("edges"), list):
                    result["edges"] = subtree_out.get("edges", [])
            if "nodes" not in result or not isinstance(result.get("nodes"), list):
                subtree_out = sample_outputs.get("prompt_3_5", {}) if isinstance(sample_outputs, dict) else {}
                if isinstance(subtree_out, dict) and isinstance(subtree_out.get("nodes"), list):
                    result["nodes"] = subtree_out.get("nodes", [])

        artifact = await write_artifact(state["run_id"], step_name, result, "json")
        # region agent log
        _debug_log(
            run_id,
            "H3",
            "nodes.py:universal_step_node:after-generate-json",
            "JSON generation output summary",
            {
                "step_id": step_id,
                "sample_stage": sample_stage,
                "result_keys": list(result.keys()) if isinstance(result, dict) else "non-dict",
                "result_nodes": len(result.get("nodes", [])) if isinstance(result, dict) and isinstance(result.get("nodes"), list) else None,
                "result_edges": len(result.get("edges", [])) if isinstance(result, dict) and isinstance(result.get("edges"), list) else None,
                "result_chunks": len(result.get("chunks", [])) if isinstance(result, dict) and isinstance(result.get("chunks"), list) else None,
            },
        )
        # endregion
    else:
        result = await generate_text(prompt_text, context)
        # Extract markdown content from code blocks if necessary
        clean_result = result
        if "```" in result:
             m = re.search(r"```(?:\w+)?\n?(.*?)\n?```", result, re.DOTALL)
             if m: clean_result = m.group(1).strip()
             
        artifact = await write_artifact(state["run_id"], step_name, clean_result, "md")
        
    # Persist sample JSON outputs so later sample steps can consume them.
    updated_sample_outputs = sample_outputs
    if sample_stage is not None and output_format == "json":
        updated_sample_outputs = dict(sample_outputs)
        updated_sample_outputs[sample_stage] = result

    # Deploy final canonical JSON into the guideline library when the chain
    # reaches the JSON compiler stage.
    if sample_stage == "prompt_6" and isinstance(result, dict):
        # Ensure core fields exist (best-effort) before writing.
        final_tree = result
        # Debug metadata: record when the artifact was produced (UTC).
        now = datetime.datetime.utcnow()
        final_tree["created_at"] = now.isoformat() + "Z"
        final_tree["created_at_unix"] = int(now.timestamp())
        file_name = state.get("file_name", "guideline.pdf")
        guideline_name = final_tree.get("name") or os.path.splitext(file_name)[0].replace("_", " ").title()
        guideline_id = final_tree.get("id") or re.sub(r"[^a-z0-9]+", "-", guideline_name.lower()).strip("-")

        final_tree["name"] = guideline_name
        final_tree["id"] = guideline_id
        final_tree["nodes"] = final_tree.get("nodes", []) or []
        final_tree["edges"] = final_tree.get("edges", []) or []

        if "root_id" not in final_tree:
            root_node = next((n for n in final_tree["nodes"] if isinstance(n, dict) and n.get("type") == "root"), None)
            final_tree["root_id"] = root_node.get("id") if root_node else "root"

        os.makedirs(FINAL_ARTIFACTS_DIR, exist_ok=True)
        safe_slug = re.sub(r"[^a-z0-9\-]", "", guideline_id.lower())
        final_path = os.path.join(FINAL_ARTIFACTS_DIR, f"{safe_slug}.json")
        with open(final_path, "w") as f:
            json.dump(final_tree, f, indent=4)

    return {
        "step_index": idx + 1,
        "current_step": step_id,
        "completed_steps": [step_id],
        "artifacts": [artifact],
        # Always return so `sample_outputs` stays present in state.
        "sample_outputs": updated_sample_outputs,
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
        # Debug metadata: record when the artifact was produced (UTC).
        now = datetime.datetime.utcnow()
        final_tree["created_at"] = now.isoformat() + "Z"
        final_tree["created_at_unix"] = int(now.timestamp())
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
