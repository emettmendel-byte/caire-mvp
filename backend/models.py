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
    current_step: Optional[str] = None
    completed_steps: List[str] = []
    artifacts: List[Dict[str, Any]] = []

# LangGraph state representation
class GraphState(TypedDict):
    run_id: str
    file_name: str
    pdf_text: str
    # Results from each node
    extracted_data: Optional[Dict[str, Any]]
    chunks: Optional[List[Dict[str, Any]]]
    decisions: Optional[Dict[str, Any]]
    tree_draft: Optional[Dict[str, Any]]
    validation_status: Optional[Dict[str, Any]]
    final_json: Optional[Dict[str, Any]]
    
    current_chunk_index: int
    chunk_decisions: List[Dict[str, Any]]
    chunk_subtrees: List[Dict[str, Any]]
    
    current_step: str
    completed_steps: Annotated[List[str], operator.add]
    artifacts: Annotated[List[Dict[str, Any]], operator.add]
    validation_retries: int
