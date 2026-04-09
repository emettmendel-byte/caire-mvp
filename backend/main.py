from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import uuid
import json
import time
from typing import Dict, Any, List, Optional
from .models import PromptUpdate, PipelineStatusResponse, GraphState
from .pipeline.prompts import (
    load_prompt_library,
    update_prompt,
    _save_library,
    get_pipeline_recipe,
    get_all_pipelines_expanded,
)
from .pipeline.langgraph_workflow import graph
from .pipeline.dynamic_workflow import dynamic_graph

app = FastAPI(title="Clinical Guideline Parsing Pipeline")

# In-memory storage for MVP. For production, use DB/Redis.
runs_db: Dict[str, PipelineStatusResponse] = {}
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

# Make sure directories exist
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")

os.makedirs(ARTIFACTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Serve the static files
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/artifacts", StaticFiles(directory=ARTIFACTS_DIR), name="artifacts")
app.mount("/pdf", StaticFiles(directory=UPLOADS_DIR), name="pdf")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/api/prompts")
def get_prompts():
    return load_prompt_library()["prompts"]

@app.put("/api/prompts")
def update_prompts(prompt: PromptUpdate):
    try:
        update_prompt(prompt.id, prompt.text)
        return {"status": "success"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/prompt-bank")
def get_prompt_bank():
    return load_prompt_library()["prompts"]

class PromptBankItem(BaseModel):
    id: str
    name: str
    text: str

@app.post("/api/prompt-bank")
def save_to_prompt_bank(item: PromptBankItem):
    lib = load_prompt_library()
    lib["prompts"][item.id] = {"id": item.id, "name": item.name, "text": item.text}
    _save_library(lib)
    return {"status": "saved", "id": item.id}

@app.delete("/api/prompt-bank/{prompt_id}")
def delete_from_prompt_bank(prompt_id: str):
    lib = load_prompt_library()
    if prompt_id not in lib["prompts"]:
        raise HTTPException(status_code=404, detail="Prompt not found")
    del lib["prompts"][prompt_id]
    _save_library(lib)
    return {"status": "deleted"}

@app.get("/api/pipelines")
def get_pipelines():
    # Expand pipelines so each step has local `prompt_text` for the UI.
    return get_all_pipelines_expanded()

class PipelineRecipe(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: List[Dict[str, Any]] = []

@app.post("/api/pipelines")
def save_pipeline(recipe: PipelineRecipe):
    lib = load_prompt_library()
    # Replace if exists, else append
    pipelines = lib.get("pipelines", [])
    pipelines = [p for p in pipelines if p["id"] != recipe.id]
    pipelines.append(recipe.dict())
    lib["pipelines"] = pipelines
    _save_library(lib)
    return {"status": "saved", "id": recipe.id}

@app.delete("/api/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: str):
    if pipeline_id == "default-governance":
        raise HTTPException(status_code=400, detail="Cannot delete the default pipeline")
    lib = load_prompt_library()
    lib["pipelines"] = [p for p in lib["pipelines"] if p["id"] != pipeline_id]
    _save_library(lib)
    return {"status": "deleted"}

@app.get("/api/status/{run_id}", response_model=PipelineStatusResponse)
def get_status(run_id: str):
    if run_id not in runs_db:
        raise HTTPException(status_code=404, detail="Run ID not found")
    return runs_db[run_id]

@app.get("/api/library")
def get_library():
    import json
    import datetime
    out = []
    if os.path.exists(ARTIFACTS_DIR):
        for f in os.listdir(ARTIFACTS_DIR):
            if f.endswith(".json"):
                path = os.path.join(ARTIFACTS_DIR, f)
                try:
                    with open(path, 'r') as file:
                        data = json.load(file)
                        stat = os.stat(path)
                        out.append({
                            "filename": f,
                            "id": data.get("id", f),
                            "name": data.get("name", "Unknown Title"),
                            "description": data.get("description", ""),
                            "date": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "path": f"/artifacts/{f}"
                        })
                except Exception as e:
                    print(f"Error parsing artifact {f}: {e}")
    out.sort(key=lambda x: x["date"], reverse=True)
    return out

@app.get("/api/pdfs")
def list_pdfs():
    import datetime
    out = []
    if os.path.exists(UPLOADS_DIR):
        for f in os.listdir(UPLOADS_DIR):
            if f.endswith(".pdf"):
                path = os.path.join(UPLOADS_DIR, f)
                stat = os.stat(path)
                out.append({
                    "filename": f,
                    "name": f.replace(".pdf", "").replace("_", " ").title(),
                    "date": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "url": f"/pdf/{f}",
                    "size": stat.st_size
                })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out

async def run_pipeline_task(run_id: str, file_name: str, extracted_text: str, pipeline_id: str = "default-governance"):
    """
    Background task to run the dynamic LangGraph workflow for the specified pipeline.

    The `pipeline_id` selects which prompt-chain recipe to use (e.g. default-governance vs sample-pipeline),
    and the dynamic graph executes those steps via the universal step node.
    """
    recipe = get_pipeline_recipe(pipeline_id)
    steps = recipe.get("steps", []) if recipe else []
    # region agent log
    _debug_log(
        run_id,
        "H1",
        "main.py:run_pipeline_task:recipe",
        "Loaded pipeline recipe",
        {"pipeline_id": pipeline_id, "recipe_found": bool(recipe), "steps_count": len(steps), "step_ids": [s.get("id") for s in steps if isinstance(s, dict)]},
    )
    # endregion
    if not steps:
        runs_db[run_id].status = "failed"
        runs_db[run_id].current_step = f"[Failure at Step: init] - No steps found for pipeline '{pipeline_id}'"
        return

    initial_state = GraphState(
        run_id=run_id,
        pipeline_id=pipeline_id,
        file_name=file_name,
        pdf_text=extracted_text,
        # Dynamic fields drive the universal step node sequence.
        pipeline_steps=steps,
        step_index=0,
        manual_repairs=None,
        red_team_report=None,
        resolved_manual=None,
        factsheet_csv=None,
        symbols_predicates=None,
        factsheet_json=None,
        validation_retries=0,
        current_step="started",
        completed_steps=[],
        artifacts=[],
        sample_outputs={},
    )
    
    runs_db[run_id].status = "running"
    
    try:
        # Dynamic graph executes the per-pipeline step list via universal_step_node.
        async for event in dynamic_graph.astream(initial_state):
            # event is a dict containing the node name and its output
            for node_name, updates in event.items():
                if isinstance(updates, dict) and "current_step" in updates:
                    runs_db[run_id].current_step = updates["current_step"]
                    runs_db[run_id].completed_steps.extend(updates.get("completed_steps", []))
                    runs_db[run_id].artifacts.extend(updates.get("artifacts", []))
        # When loop finishes, the graph reached END
        runs_db[run_id].status = "completed"
        runs_db[run_id].current_step = "done"
    except Exception as e:
        last_step = runs_db[run_id].current_step or "unknown"
        error_msg = f"[Failure at Step: {last_step}] - {str(e)}"
        print(f"Exception during pipeline {run_id}: {error_msg}")
        runs_db[run_id].status = "failed"
        runs_db[run_id].current_step = error_msg


def _extract_text_from_pdf(pdf_path: str) -> str:
    """Helper to extract text from a physical PDF file."""
    from pypdf import PdfReader
    extracted_text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            extracted_text += page.extract_text() + "\n"
        return extracted_text
    except Exception as e:
        raise Exception(f"Failed to extract PDF text: {e}")

@app.post("/api/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    pipeline_id: str = "default-governance"
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Must be a PDF file")

    contents = await file.read()
    pdf_path = os.path.join(UPLOADS_DIR, file.filename)
    with open(pdf_path, "wb") as f:
        f.write(contents)
    
    try:
        extracted_text = _extract_text_from_pdf(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    run_id = str(uuid.uuid4())
    runs_db[run_id] = PipelineStatusResponse(
        run_id=run_id,
        status="pending",
        pipeline_id=pipeline_id,
        current_step="PDF Uploaded",
        completed_steps=[],
        artifacts=[]
    )
    
    background_tasks.add_task(run_pipeline_task, run_id, file.filename, extracted_text, pipeline_id)
    return {"run_id": run_id, "status": "Pipeline queued"}

@app.post("/api/reprocess/{filename}")
async def reprocess_pdf(
    filename: str,
    background_tasks: BackgroundTasks,
    pipeline_id: str = "default-governance"
):
    pdf_path = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")
        
    try:
        extracted_text = _extract_text_from_pdf(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    run_id = str(uuid.uuid4())
    runs_db[run_id] = PipelineStatusResponse(
        run_id=run_id,
        status="pending",
        pipeline_id=pipeline_id,
        current_step="Starting Reprocessing",
        completed_steps=[],
        artifacts=[]
    )
    
    background_tasks.add_task(run_pipeline_task, run_id, filename, extracted_text, pipeline_id)
    return {"run_id": run_id, "status": "Pipeline queued"}


@app.delete("/api/library/{filename}")
def delete_guideline(filename: str):
    path = os.path.join(ARTIFACTS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="File not found")

@app.delete("/api/pdfs/{filename}")
def delete_pdf(filename: str):
    path = os.path.join(UPLOADS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="File not found")
