from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import uuid
import uuid
from typing import Dict, Any, List
from .models import PromptUpdate, PipelineStatusResponse, GraphState
from .pipeline.prompts import load_prompts, update_prompt
from .pipeline.langgraph_workflow import graph

app = FastAPI(title="Clinical Guideline Parsing Pipeline")

# In-memory storage for MVP. For production, use DB/Redis.
runs_db: Dict[str, PipelineStatusResponse] = {}

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
    return load_prompts()

@app.put("/api/prompts")
def update_prompts(prompt: PromptUpdate):
    try:
        update_prompt(prompt.id, prompt.text)
        return {"status": "success"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

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

async def run_pipeline_task(run_id: str, file_name: str, extracted_text: str):
    """Background task to run the LangGraph workflow."""
    
    # Initialize the state map
    initial_state = GraphState(
        run_id=run_id,
        file_name=file_name,
        pdf_text=extracted_text,
        extracted_data=None,
        chunks=None,
        decisions=None,
        tree_draft=None,
        validation_status=None,
        final_json=None,
        current_chunk_index=0,
        chunk_decisions=[],
        chunk_subtrees=[],
        current_step="started",
        completed_steps=[],
        artifacts=[],
        validation_retries=0
    )
    
    runs_db[run_id].status = "running"
    
    try:
        # We need an async iterator to get updates, or we can use graph.ainvoke / astream
        # .astream() yields events with state updates as they happen
        async for event in graph.astream(initial_state):
            # event is a dict containing the node name and its output
            # For example: {"extract_text": {"extracted_data": ...}}
            for node_name, updates in event.items():
                if isinstance(updates, dict) and "current_step" in updates:
                    runs_db[run_id].current_step = updates["current_step"]
                    runs_db[run_id].completed_steps.extend(updates.get("completed_steps", []))
                    runs_db[run_id].artifacts.extend(updates.get("artifacts", []))
                    
        # When loop finishes, the graph reached END
        runs_db[run_id].status = "completed"
        runs_db[run_id].current_step = "done"

    except Exception as e:
        print(f"Exception during pipeline {run_id}: {e}")
        runs_db[run_id].status = "failed"
        runs_db[run_id].current_step = str(e)


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
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Must be a PDF file")

    # Read and save the file
    contents = await file.read()
    pdf_path = os.path.join(UPLOADS_DIR, file.filename)
    with open(pdf_path, "wb") as f:
        f.write(contents)
    
    # Extract text
    try:
        extracted_text = _extract_text_from_pdf(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    run_id = str(uuid.uuid4())
    runs_db[run_id] = PipelineStatusResponse(
        run_id=run_id,
        status="pending",
        current_step="PDF Uploaded",
        completed_steps=[],
        artifacts=[]
    )
    
    # Start LangGraph processing in background
    background_tasks.add_task(run_pipeline_task, run_id, file.filename, extracted_text)
    
    return {"run_id": run_id, "status": "Pipeline queued"}

@app.post("/api/reprocess/{filename}")
async def reprocess_pdf(filename: str, background_tasks: BackgroundTasks):
    pdf_path = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")
        
    # Extract text
    try:
        extracted_text = _extract_text_from_pdf(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    run_id = str(uuid.uuid4())
    runs_db[run_id] = PipelineStatusResponse(
        run_id=run_id,
        status="pending",
        current_step="Starting Reprocessing",
        completed_steps=[],
        artifacts=[]
    )
    
    background_tasks.add_task(run_pipeline_task, run_id, filename, extracted_text)
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
