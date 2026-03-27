import json
import os
from typing import Dict, Any

PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "prompts.json")

DEFAULT_PROMPTS = {
    "prompt_1": {
        "id": "prompt_1",
        "description": "Text Extraction Agent",
        "text": """You are a PDF extractor. Given raw PDF content or OCR text from a clinical guideline, extract all readable text, headings, tables, and decision-like phrases (e.g., "if fever >38.5°C, then refer"). Ignore images/footers.

Input: The payload below contains the pdf_text.

Output ONLY valid JSON:
{
  "full_text": "complete extracted text",
  "headings": ["list of section titles"],
  "tables": [{"title": "str", "rows": [["cell1", "cell2"], ...]}],
  "decision_phrases": ["raw phrases like 'If X, then Y'"]
}"""
    },
    "prompt_2": {
        "id": "prompt_2",
        "description": "Chunking Agent",
        "text": """Segment the guideline into logical chunks focused on decisions. Prioritize sections with conditionals (if/then), thresholds, flows. Chunk size: 500-1000 words or by heading.

Input: The payload below contains the full_text from Prompt 1 and headings.

Output ONLY valid JSON:
{
  "chunks": [
    {
      "id": "unique_id",
      "title": "chunk title",
      "content": "text",
      "type": "decision|flow|criteria|other"
    }
  ]
}"""
    },
    "prompt_3": {
        "id": "prompt_3",
        "description": "Decision Point Identifier Agent",
        "text": """You are a clinical decision-point extractor. Analyse the single guideline chunk provided and identify every decision node it contains.

Output EXACTLY according to this JSON Schema:
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "type", "label", "description", "origin"],
        "properties": {
          "id": { "type": "string", "description": "short snake_case id" },
          "type": { "type": "string", "enum": ["root", "question", "outcome"] },
          "label": { "type": "string", "description": "concise node name" },
          "description": { "type": "string", "description": "detailed clinical explanation" },
          "origin": { "type": ["string", "null"], "description": "id of parent node" },
          "output_type": { "type": "string", "enum": ["string", "number", "boolean"] },
          "output_map": { "type": "object", "additionalProperties": { "type": "string" }, "description": "maps results to target node ids" },
          "condition": { "type": "object", "properties": { "variable": {"type":"string"}, "operator": {"type":"string"}, "threshold": {"type":"string"} } },
          "metadata": { "type": "object", "properties": { "question": { "type": "object" } } }
        }
      }
    },
    "edges": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["source_id", "target_id", "label"],
        "properties": {
          "source_id": { "type": "string" },
          "target_id": { "type": "string" },
          "label": { "type": "string" }
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
    "prompt_3_5": {
        "id": "prompt_3_5",
        "description": "Subtree Builder Agent",
        "text": """You receive a list of decision nodes and edges extracted from ONE guideline chunk. Your task is to validate and complete them so they form a consistent sub-graph fragment.

Rules:
1. Every node referenced in an edge must appear in the nodes list. Add placeholder outcome nodes if missing.
2. Every question node must have both output_map and at least one edge per answer.
3. Do NOT introduce loops.
4. Keep all id values as short snake_case strings.
5. Ensure origin fields are consistent with edges.

Input: The payload below contains {chunk, decisions: {nodes, edges}}.

Output ONLY valid JSON — no prose, no markdown fences:
{
  \"nodes\": [ /* same format as input, completed and validated */ ],
  \"edges\": [ {\"source_id\": \"...\", \"target_id\": \"...\", \"label\": \"...\"} ]
}"""
    },
    "prompt_4": {
        "id": "prompt_4",
        "description": "Tree Merger Agent",
        "text": """You receive a list of sub-graph fragments (each with nodes[] and edges[]). Merge them into a single master decision tree.

Rules:
1. Deduplicate nodes by id. If the same id appears in multiple fragments keep the most complete version.
2. Connect fragments: find question nodes whose output_map target does not yet exist in any fragment — link them to the root node of the next fragment instead.
3. There must be exactly ONE root node (type = \"root\"). If multiple roots exist, pick the most general one and make the others question nodes.
4. Every outcome node must have type = \"outcome\" and no output_map.
5. Return a flat node list and a complete edge list — do NOT use nested trees or $ref pointers.

Input: The payload below contains a list of {nodes, edges} fragment objects.

Output ONLY valid JSON — no prose, no markdown fences:
{
  \"nodes\": [ /* all merged nodes */ ],
  \"edges\": [ {\"source_id\": \"...\", \"target_id\": \"...\", \"label\": \"...\"} ]
}"""
    },
    "prompt_5": {
        "id": "prompt_5",
        "description": "Validator Agent",
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

Output ONLY valid JSON — no prose, no markdown fences, no reasoning:
{
  \"valid\": true,
  \"issues\": [\"list of max 10 critical issues found and fixed\"],
  \"nodes\": [ /* corrected node list */ ],
  \"edges\": [ {\"source_id\": \"...\", \"target_id\": \"...\", \"label\": \"...\"} ]
}"""
    },
    "prompt_6": {
        "id": "prompt_6",
        "description": "JSON Compiler Agent",
        "text": """You are the final step in a clinical guideline parsing pipeline. You receive validated nodes[] and edges[] and must produce the canonical CAIRE decision-tree JSON document.

Output EXACTLY according to this Schema:
{
  "type": "object",
  "required": ["id", "version", "name", "description", "root_id", "nodes", "edges"],
  "properties": {
    "id": { "type": "string", "description": "kebab-case slug derived from guideline name" },
    "version": { "type": "string", "default": "1.0.0" },
    "name": { "type": "string", "description": "human-readable clinical title" },
    "description": { "type": "string", "description": "one sentence summary" },
    "root_id": { "type": "string", "description": "id of the root node" },
    "nodes": { "type": "array", "description": "List of clinical logic nodes" },
    "edges": { "type": "array", "description": "List of connections between nodes" }
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

def load_prompts() -> Dict[str, Any]:
    """Loads all prompts from file, or returns defaults if missing."""
    if not os.path.exists(PROMPTS_FILE):
        _save_prompts(DEFAULT_PROMPTS)
        return DEFAULT_PROMPTS
    try:
        with open(PROMPTS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return DEFAULT_PROMPTS

def _save_prompts(prompts: Dict[str, Any]):
    """Saves prompts dictionary to file."""
    with open(PROMPTS_FILE, "w") as f:
        json.dump(prompts, f, indent=4)

def update_prompt(prompt_id: str, new_text: str):
    prompts = load_prompts()
    if prompt_id in prompts:
        prompts[prompt_id]["text"] = new_text
        _save_prompts(prompts)
    else:
        raise KeyError(f"Prompt {prompt_id} not found")
        
def get_prompt_text(prompt_id: str) -> str:
    prompts = load_prompts()
    if prompt_id in prompts:
        return prompts[prompt_id]["text"]
    return ""
