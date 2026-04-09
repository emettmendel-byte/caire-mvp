import json
import os
from typing import Dict, Any, List, Optional

PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "prompts.json")

# ── Migration Structure ──────────────────────────────────────────────────────
# The old flat structure: { "prompt_a1": { "id": "prompt_a1", "text": "..." }, ... }
# The new library structure:
# {
#   "prompts": { "prompt_id": { "id": "prompt_id", "name": "...", "text": "..." } },
#   "pipelines": [ { "id": "default", "name": "...", "steps": { "a1": "prompt_id" } } ]
# }

DEFAULT_PROMPTS = {
    "a1_default": {
        "id": "a1_default",
        "name": "Standard Manual Repair (A1)",
        "text": """You are a clinical protocol analyst.

TASK: Identify gaps, contradictions, and ambiguities in the manual that must be resolved.

INPUTS: manual.pdf content provided.

OUTPUTS: 
- DraftAddendum.md (proposed fixes)
- Queries.md (questions for Ministry of Health)

RULES:
- Do not invent clinical content.
- For every gap, propose a placeholder rule + specific question.
- Prioritize emergency referral clarity, missingness handling, dosage details.
- Keep all findings traceable to source page/section."""
    },
    "a2_default": {
        "id": "a2_default",
        "name": "Hostile Red-team Audit (A2)",
        "text": """You are a hostile clinical red-team auditor.

TASK: Attack the manual + addendum for silent killers and logic gaps.

INPUTS: manual.pdf, DraftAddendum.md content provided.

OUTPUT: manualredteamreport.md

FOCUS:
- Missing data failures
- Stockout failures  
- Loop risks
- Dead ends
- Emergency bypass paths
- Rank by clinical severity"""
    },
    "a2_repair_default": {
        "id": "a2_repair_default",
        "name": "Verbatim Repair Drafting (A2-repair)",
        "text": """You are a clinical auditor producing precise manual repairs.

TASK: Draft verbatim text amendments for each red-team finding.

INPUTS: manualredteamreport.md, manual.pdf content provided.

OUTPUT: manualdraftrepairs.md

RULES:
- Do not invent clinical protocols.
- Unknown fallback = referral.
- Minimal, exact, auditable fixes.
- Ready to merge into single resolved manual."""
    },
    "b1_default": {
        "id": "b1_default",
        "name": "Atomic Fact Extraction (B1)",
        "text": """You are a clinical knowledge engineer.

TASK: Extract atomic clinical facts and workflow facts.

INPUTS: ResolvedManual.md (consolidated repair text).

OUTPUT: factsheet.csv

SCHEMA:
factid,category,symptom|action|drug|workflow,content,priorityweight,source,page,provenance

RULES:
- Split compound statements into atomic facts.
- Separate clinical from workflow content.
- Include source provenance for every fact.
- Do not invent facts."""
    },
    "b2_default": {
        "id": "b2_default",
        "name": "Hungarian Symbols & Predicates (B2)",
        "text": """You are a clinical data modeler.

TASK: Convert facts into symbols and predicates.

INPUTS: factsheet.csv provided.

OUTPUTS:
- symbols.json (v/p/c/m variables with Hungarian prefixes)
- predicates.json (boolean predicates with missingness-safe defaults)

RULES:
- vslug = raw observation
- pslug = derived boolean (1/0 only)
- cslug = context toggle
- Every predicate must have failsafevalue.
- Missing temp → pfever = 1 (high risk default).
- BE CONCISE: Use short fragments for descriptions. Avoid prose. Keep the output as compact as possible.

CRITICAL: Return ONLY valid JSON containing {"symbols": [...], "predicates": [...]}."""
    },
    "b6_default": {
        "id": "b6_default",
        "name": "Decision-tree Factsheet Generator (B6)",
        "text": """You are a clinical decision-tree compiler.

TASK: Build the single canonical factsheet.json decision tree.

INPUTS: ResolvedManual.md, factsheet.csv, symbols.json, predicates.json provided.

OUTPUT: factsheet.json (MUST match exact schema)

RULES:
- root_id = \"root\"
- Node types: root/question/outcome only
- Every clinical decision = question node
- Every endpoint = outcome node  
- Thresholds → condition {variable, operator, threshold}
- Multi-answer → output_map
- Units/options → metadata.question
- Emergency referral = direct high-priority path
- Every node/edge = traceable to ResolvedManual.md
- Do not invent clinical content
- Placeholder nodes must be flagged clearly

CRITICAL: Return ONLY valid JSON schema-compliant document. No preamble, no postamble."""
    },
    "d5_default": {
        "id": "d5_default",
        "name": "Clinical Safety Validator (D5)",
        "text": """You are a clinical tree validator.

TASK: Validate factsheet.json for completeness, safety, and schema compliance.

INPUTS: factsheet.json, ResolvedManual.md provided.

OUTPUTS:
- validation_report.md (issues found)
- factsheet_validated.json (fixed version)

CHECKS:
- Schema compliance (required fields, types, lengths)
- Edge integrity (every edge points to existing node)
- No dead ends (every question has ≥1 downstream edge)
- Emergency referral paths are direct/visible
- Conservative missingness handling preserved
- Every clinical decision point is represented"""
    },
    "g1_default": {
        "id": "g1_default",
        "name": "Deployment Governance (G1)",
        "text": """You are a deployment governance engineer.

TASK: Final manifest and audit trail.

INPUTS: factsheet_validated.json + all artifacts provided.

OUTPUTS:
- manifest.json (hashes, versions, provenance)
- governance_log.md (human signoffs needed?)

RULES:
- SHA-256 hash every artifact.
- List all manual repairs and clinician signoffs.
- Flag any open_questions from validation.

CRITICAL: Return ONLY JSON as primary output, then MD log separated by delimiter."""
    },
    # ── Sample Pipeline Prompts ──────────────────────────────────────────
    "sample_extract": {
        "id": "sample_extract",
        "name": "Sample: Text Extraction",
        "text": """You are a PDF extractor. Given raw PDF content or OCR text from a clinical guideline, extract all readable text, headings, tables, and decision-like phrases (e.g., \"if fever >38.5°C, then refer\"). Ignore images/footers.

Input: The payload below contains the pdf_text.

CRITICAL: Output ONLY valid JSON. No preamble, no reasoning, no markdown fences.
{
  \"full_text\": \"complete extracted text\",
  \"headings\": [\"list of section titles\"],
  \"tables\": [{\"title\": \"str\", \"rows\": [[\"cell1\", \"cell2\"], ...]}],
  \"decision_phrases\": [\"raw phrases like 'If X, then Y'\"]
}"""
    },
    "sample_chunk": {
        "id": "sample_chunk",
        "name": "Sample: Chunking Agent",
        "text": """Segment the guideline into logical chunks focused on decisions. Prioritize sections with conditionals (if/then), thresholds, flows. Chunk size: 500-1000 words or by heading.

Input: The payload below contains the full_text from Prompt 1 and headings.

CRITICAL: Output ONLY valid JSON. No preamble, no reasoning, no markdown fences.
{
  \"chunks\": [
    {
      \"id\": \"unique_id\",
      \"title\": \"chunk title\",
      \"content\": \"text\",
      \"type\": \"decision|flow|criteria|other\"
    }
  ]
}"""
    },
    "sample_id": {
        "id": "sample_id",
        "name": "Sample: Decision ID",
        "text": """You are a clinical decision-point extractor. Analyse the single guideline chunk provided and identify every decision node it contains.

Output EXACTLY according to this JSON Schema:
{
  \"$schema\": \"http://json-schema.org/draft-07/schema#\",
  \"type\": \"object\",
  \"properties\": {
    \"nodes\": {
      \"type\": \"array\",
      \"items\": {
        \"type\": \"object\",
        \"required\": [\"id\", \"type\", \"label\", \"description\", \"origin\"],
        \"properties\": {
          \"id\": { \"type\": \"string\", \"description\": \"short snake_case id\" },
          \"type\": { \"type\": \"string\", \"enum\": [\"root\", \"question\", \"outcome\"] },
          \"label\": { \"type\": \"string\", \"description\": \"concise node name\" },
          \"description\": { \"type\": \"string\", \"description\": \"detailed clinical explanation\" },
          \"origin\": { \"type\": [\"string\", \"null\"], \"description\": \"id of parent node\" },
          \"output_type\": { \"type\": \"string\", \"enum\": [\"string\", \"number\", \"boolean\"] },
          \"output_map\": { \"type\": \"object\", \"additionalProperties\": { \"type\": \"string\" }, \"description\": \"maps results to target node ids\" },
          \"condition\": { \"type\": \"object\", \"properties\": { \"variable\": {\"type\":\"string\"}, \"operator\": {\"type\":\"string\"}, \"threshold\": {\"type\":\"string\"} } },
          \"metadata\": { \"type\": \"object\", \"properties\": { \"question\": { \"type\": \"object\" } } }
        }
      }
    },
    \"edges\": {
      \"type\": \"array\",
      \"items\": {
        \"type\": \"object\",
        \"required\": [\"source_id\", \"target_id\", \"label\"],
        \"properties\": {
          \"source_id\": { \"type\": \"string\" },
          \"target_id\": { \"type\": \"string\" },
          \"label\": { \"type\": \"string\" }
        }
      }
    }
  }
}

Rules:
- Root node must have origin: null and type: \"root\".
- Question nodes must have output_map and metadata.
- Outcome nodes have NO outgoing edges.
- DO NOT hallucinate examples. ONLY use content found in the provided clinical text.

Input: The payload below contains ONE chunk.

Output ONLY valid JSON — no preamble, no markdown fences, no text whatsoever."""
    },
    "sample_subtree": {
        "id": "sample_subtree",
        "name": "Sample: Subtree Builder",
        "text": """You receive a list of decision nodes and edges extracted from ONE guideline chunk. Your task is to validate and complete them so they form a consistent sub-graph fragment.

Rules:
1. Every node referenced in an edge must appear in the nodes list. Add placeholder outcome nodes if missing.
2. Every question node must have both output_map and at least one edge per answer.
3. Do NOT introduce loops.
4. Keep all id values as short snake_case strings.
5. Ensure origin fields are consistent with edges.

Input: The payload below contains {chunk, decisions: {nodes, edges}}.

CRITICAL: Output ONLY valid JSON. No preamble, no reasoning, no markdown fences.
{
  \"nodes\": [ /* same format as input, completed and validated */ ],
  \"edges\": [ {\"source_id\": \"...\", \"target_id\": \"...\", \"label\": \"...\"} ]
}"""
    },
    "sample_merge": {
        "id": "sample_merge",
        "name": "Sample: Tree Merger",
        "text": """You receive a list of sub-graph fragments (each with nodes[] and edges[]). Merge them into a single master decision tree.

Rules:
1. Deduplicate nodes by id. If the same id appears in multiple fragments keep the most complete version.
2. Connect fragments: find question nodes whose output_map target does not yet exist in any fragment — link them to the root node of the next fragment instead.
3. There must be exactly ONE root node (type = \"root\"). If multiple roots exist, pick the most general one and make the others question nodes.
4. Every outcome node must have type = \"outcome\" and no output_map.
5. Return a flat node list and a complete edge list — do NOT use nested trees or $ref pointers.

Input: The payload below contains a list of {nodes, edges} fragment objects.

CRITICAL: Output ONLY valid JSON. No preamble, no reasoning, no markdown fences.
{
  \"nodes\": [ /* all merged nodes */ ],
  \"edges\": [ {\"source_id\": \"...\", \"target_id\": \"...\", \"label\": \"...\"} ]
}"""
    },
    "sample_validate": {
        "id": "sample_validate",
        "name": "Sample: Validator Agent",
        "text": """You receive a merged decision tree (nodes[] and edges[]). Validate it and fix any problems.

Checks to perform:
1. Exactly one root node (type = \"root\").
2. No orphan nodes (every non-root node is reachable from root via edges).
3. No duplicate node ids.
4. No cycles in the graph.
5. Every edge source_id and target_id exists in the nodes list.
6. Every question node has at least 2 edges leaving it.
7. Every outcome node has 0 edges leaving it.

If any check fails, fix the nodes and edges directly — remove orphans, add missing edges, rename duplicate ids.

Input: The payload below contains {nodes, edges, decisions} from the merger step.

CRITICAL: Output ONLY valid JSON. No preamble, no reasoning (no <think> tags), no markdown fences.
{
  \"valid\": true,
  \"issues\": [\"list of max 10 critical issues found and fixed\"],
  \"nodes\": [ /* corrected node list */ ],
  \"edges\": [ {\"source_id\": \"...\", \"target_id\": \"...\", \"label\": \"...\"} ]
}"""
    },
    "sample_compile": {
        "id": "sample_compile",
        "name": "Sample: JSON Compiler",
        "text": """You are the final step in a clinical guideline parsing pipeline. You receive validated nodes[] and edges[] and must produce the canonical CAIRE decision-tree JSON document.

Output EXACTLY according to this Schema:
{
  \"type\": \"object\",
  \"required\": [\"id\", \"version\", \"name\", \"description\", \"root_id\", \"nodes\", \"edges\"],
  \"properties\": {
    \"id\": { \"type\": \"string\", \"description\": \"kebab-case slug derived from guideline name\" },
    \"version\": { \"type\": \"string\", \"default\": \"1.0.0\" },
    \"name\": { \"type\": \"string\", \"description\": \"human-readable clinical title\" },
    \"description\": { \"type\": \"string\", \"description\": \"one sentence summary\" },
    \"root_id\": { \"type\": \"string\", \"description\": \"id of the root node\" },
    \"nodes\": { \"type\": \"array\", \"description\": \"List of clinical logic nodes\" },
    \"edges\": { \"type\": \"array\", \"description\": \"List of connections between nodes\" }
  }
}

Rules:
- \"id\" must be a unique slug (e.g. \"asthma-emergency-triage\").
- \"root_id\" must match the ID of the node with type \"root\".
- DO NOT use sample identifiers like \"paediatric-fever\". ONLY use information from the source text.
- Output ONLY the JSON object — no prose, no markdown, no reasoning.

Input: The payload below contains file_name, nodes[], edges[], and validation summary."""
    }
}

DEFAULT_PIPELINES = [
    {
        "id": "default-governance",
        "name": "Clinical Governance Standard",
        "description": "Standard 8-stage clinical governance pipeline with audit, red-teaming, and fact extraction.",
        "steps": [
            {"id": "s1", "name": "Manual Repair", "prompt_id": "a1_default"},
            {"id": "s2", "name": "Red-team Audit", "prompt_id": "a2_default"},
            {"id": "s3", "name": "Repair Drafting", "prompt_id": "a2_repair_default"},
            {"id": "s4", "name": "Facts Extraction", "prompt_id": "b1_default"},
            {"id": "s5", "name": "Symbols & Predicates", "prompt_id": "b2_default"},
            {"id": "s6", "name": "Factsheet Builder", "prompt_id": "b6_default"},
            {"id": "s7", "name": "Tree Validation", "prompt_id": "d5_default"},
            {"id": "s8", "name": "Governance Final", "prompt_id": "g1_default"}
        ]
    },
    {
        "id": "sample-pipeline",
        "name": "Sample Pipeline",
        "description": "A simplified extraction pipeline focusing on chunking, merging, and validation.",
        "steps": [
            {"id": "s1", "name": "Text Extraction", "prompt_id": "sample_extract"},
            {"id": "s2", "name": "Chunking", "prompt_id": "sample_chunk"},
            {"id": "s3", "name": "Decision ID", "prompt_id": "sample_id"},
            {"id": "s4", "name": "Subtree Builder", "prompt_id": "sample_subtree"},
            {"id": "s5", "name": "Tree Merger", "prompt_id": "sample_merge"},
            {"id": "s6", "name": "Validator", "prompt_id": "sample_validate"}
        ]
    }
]

def load_prompt_library() -> Dict[str, Any]:
    if not os.path.exists(PROMPTS_FILE):
        data = {"prompts": DEFAULT_PROMPTS, "pipelines": DEFAULT_PIPELINES}
        _save_library(data)
        return data
    
    try:
        with open(PROMPTS_FILE, "r") as f:
            data = json.load(f)
            
        # Migrate old structure if detected
        if "prompts" not in data:
            new_data = {"prompts": {}, "pipelines": DEFAULT_PIPELINES}
            for k, v in data.items():
                if isinstance(v, dict) and "text" in v:
                    new_id = f"{k}_v1"
                    new_data["prompts"][new_id] = {
                        "id": new_id,
                        "name": v.get("description", k),
                        "text": v["text"]
                    }
            _save_library(new_data)
            return new_data

        # ── Migration to Array-based Pipelines ──────────────────────────
        modified = False
        for pl in data.get("pipelines", []):
            if isinstance(pl.get("steps"), dict):
                # Convert object-based steps to array
                new_steps = []
                for i, (k, pid) in enumerate(pl["steps"].items()):
                    new_steps.append({
                        "id": f"s{i+1}", 
                        "name": k.replace("_", " ").title(),
                        "prompt_id": pid
                    })
                pl["steps"] = new_steps
                modified = True
        
        if modified:
            _save_library(data)
            
        return data
    except Exception as e:
        print(f"Error loading prompt library: {e}")
        return {"prompts": DEFAULT_PROMPTS, "pipelines": DEFAULT_PIPELINES}

def _save_library(data: Dict[str, Any]):
    with open(PROMPTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def _expand_pipeline(pipeline: Dict[str, Any], lib: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures each pipeline step contains a local `prompt_text` so the UI no longer
    depends on an external prompt bank.
    """
    expanded = dict(pipeline)
    steps = expanded.get("steps", [])

    # Defensive: older/incorrect stored data might use a dict.
    if isinstance(steps, dict):
        steps_list: List[Dict[str, Any]] = []
        for i, (k, prompt_id) in enumerate(steps.items()):
            steps_list.append({"id": f"s{i+1}", "name": k.replace("_", " ").title(), "prompt_id": prompt_id})
        steps = steps_list

    if not isinstance(steps, list):
        steps = []

    expanded_steps: List[Dict[str, Any]] = []
    for step in steps:
        s = dict(step) if isinstance(step, dict) else {}
        if (not s.get("prompt_text")) and s.get("prompt_id"):
            prompt_id = s.get("prompt_id")
            prompt = lib.get("prompts", {}).get(prompt_id, {})
            s["prompt_text"] = prompt.get("text", "")
            s["prompt_name"] = prompt.get("name", prompt_id)
        expanded_steps.append(s)

    expanded["steps"] = expanded_steps
    return expanded

def get_all_pipelines_expanded() -> List[Dict[str, Any]]:
    lib = load_prompt_library()
    return [_expand_pipeline(p, lib) for p in lib.get("pipelines", [])]

def get_pipeline_recipe(pipeline_id: str) -> Optional[Dict[str, Any]]:
    lib = load_prompt_library()
    for p in lib.get("pipelines", []):
        if p["id"] == pipeline_id:
            return _expand_pipeline(p, lib)
    return _expand_pipeline(lib["pipelines"][0], lib) if lib.get("pipelines") else None

def get_step_config(pipeline_id: str, step_index: int) -> Optional[Dict[str, Any]]:
    """Gets the configuration for a specific step in a dynamic pipeline."""
    recipe = get_pipeline_recipe(pipeline_id)
    if not recipe or not isinstance(recipe.get("steps"), list):
        return None
    
    if 0 <= step_index < len(recipe["steps"]):
        return recipe["steps"][step_index]
    return None

def get_prompt_text(pipeline_id: str, step_key: str = None, step_index: int = None) -> str:
    """
    Gets the prompt text for a specific step.
    Supports legacy step_key lookup (for static nodes) and new step_index lookup (for dynamic nodes).
    """
    lib = load_prompt_library()
    recipe = get_pipeline_recipe(pipeline_id)
    if not recipe:
        return ""
    
    prompt_id = None
    steps = recipe.get("steps", [])
    
    if step_index is not None and isinstance(steps, list):
        if 0 <= step_index < len(steps):
            prompt_id = steps[step_index].get("prompt_id")
    elif step_key is not None:
        if isinstance(steps, dict):
            prompt_id = steps.get(step_key)
        elif isinstance(steps, list):
            # Fallback for array-based pipelines: try to find by step name or id if they match the key
            for s in steps:
                if s.get("id") == step_key or s.get("name") == step_key:
                    prompt_id = s.get("prompt_id")
                    break
    
    if not prompt_id:
        return ""
    
    prompt = lib["prompts"].get(prompt_id)
    return prompt["text"] if prompt else ""

# Legacy helpers for backward compatibility or simple use cases
def load_prompts():
    return load_prompt_library()["prompts"]

def update_prompt(prompt_id: str, new_text: str):
    lib = load_prompt_library()
    if prompt_id in lib["prompts"]:
        lib["prompts"][prompt_id]["text"] = new_text
        _save_library(lib)
    else:
        raise KeyError(f"Prompt {prompt_id} not found in bank")
