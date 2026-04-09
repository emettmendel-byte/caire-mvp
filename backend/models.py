from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import operator
from typing_extensions import Annotated
from typing import TypedDict

class PromptUpdate(BaseModel):
    id: str
    text: str

class PipelineStatusResponse(BaseModel):
    run_id: str
    status: str
    pipeline_id: Optional[str] = "default-governance"
    current_step: Optional[str] = None
    completed_steps: List[str] = []
    artifacts: List[Dict[str, Any]] = []

# LangGraph state representation
class GraphState(TypedDict):
    run_id: str
    pipeline_id: str
    file_name: str
    pdf_text: str
    
    # ── Dynamic Execution Data ──
    # The list of prompt IDs to run, from the recipe
    pipeline_steps: List[Dict[str, Any]] 
    # The index of the current step being executed
    step_index: int
    
    # ── Phase A: Audit & Repair (Legacy support or for specific nodes) ──
    manual_repairs: Optional[str]
    red_team_report: Optional[str]
    resolved_manual: Optional[str]
    
    # ── Phase B: Structuring (Legacy support) ──
    factsheet_csv: Optional[str]
    symbols_predicates: Optional[Dict[str, Any]]
    factsheet_json: Optional[Dict[str, Any]]
    
    current_step: str
    completed_steps: Annotated[List[str], operator.add]
    # All artifacts generated across the entire pipeline
    artifacts: Annotated[List[Dict[str, Any]], operator.add]
    validation_retries: int

    # Special-case state for the built-in `sample-pipeline` prompt chain.
    # Stores parsed JSON outputs keyed by `prompt_id` so later sample steps
    # can receive the exact structured inputs they expect.
    sample_outputs: Dict[str, Any]
