# CAIRE — Clinical AI Reasoning Engine

CAIRE is a production-ready platform for transforming clinical guideline PDFs into machine-executable JSON decision trees. Upload a PDF, select a pipeline, and CAIRE runs a chain of LLM agents that audit, repair, extract, and compile the guideline into a structured, schema-validated artifact ready for downstream clinical decision-support systems.

---

## What It Does

Clinical guidelines are written for humans — dense, ambiguous, and full of implied logic. CAIRE automates the hard parts:

1. **Ingests** a PDF (clinical protocol, treatment manual, etc.) via a drag-and-drop UI or API.
2. **Runs a configurable multi-step LLM pipeline** where each step is a specialized agent with a distinct role (auditor, fact extractor, decision compiler, validator, etc.).
3. **Produces a structured JSON decision tree** conforming to a strict schema (`schema.json`) — a graph of `root`, `question`, and `outcome` nodes connected by labeled edges, with thresholds, missingness-safe defaults, and emergency referral paths baked in.
4. **Stores all artifacts** in a searchable library so you can revisit, reprocess, or delete past runs.

The entire pipeline runs locally using [Ollama](https://ollama.com/) — no cloud LLM calls, no data leaving your machine.

---

## How It Works

### Architecture Overview

```
Browser (React/Vite)
    │
    ▼
FastAPI (port 4001)
    ├── /api/upload          → Accept PDF, queue pipeline run
    ├── /api/status/{run_id} → Poll live step progress
    ├── /api/library         → Browse completed JSON artifacts
    ├── /api/pipelines       → CRUD for pipeline recipes
    └── /api/prompt-bank     → CRUD for prompt templates
    │
    ▼
Dynamic LangGraph Workflow
    └── Universal Step Node  → loops over pipeline_steps[], calling Ollama at each step
    │
    ▼
Ollama (local LLM — deepseek-r1:latest)
```

### The Dynamic Pipeline Engine

The core innovation is a **universal step node** built on LangGraph. Rather than hard-coding a fixed set of agent nodes, CAIRE compiles any pipeline _recipe_ into a single looping graph:

```
START → execute_step → [should_continue?] → execute_step → ... → END
```

Each iteration reads the next step from `pipeline_steps[]`, fetches the associated prompt from the prompt bank, injects the accumulated context (PDF text + prior step outputs), calls the LLM, and advances `step_index`. This means you can build any pipeline without touching Python code.

### Pipeline Recipes

Pipelines are defined in `prompts.json` as named sequences of prompt references:

**Clinical Governance Standard** (8 stages):

| Step | Agent Role | Output |
|------|-----------|--------|
| A1 – Manual Repair | Identify gaps, contradictions, and ambiguities | `DraftAddendum.md`, `Queries.md` |
| A2 – Red-team Audit | Hostile review for silent clinical killers | `manualredteamreport.md` |
| A2-Repair – Repair Drafting | Draft verbatim text amendments for each finding | `manualdraftrepairs.md` |
| B1 – Fact Extraction | Extract atomic clinical + workflow facts | `factsheet.csv` |
| B2 – Symbols & Predicates | Convert facts to Hungarian-prefix symbols and missingness-safe predicates | `symbols.json`, `predicates.json` |
| B6 – Decision Tree Builder | Compile the canonical JSON decision tree | `factsheet.json` |
| D5 – Safety Validator | Validate schema compliance, dead ends, edge integrity | `validation_report.md`, `factsheet_validated.json` |
| G1 – Governance Final | SHA-256 manifest, audit trail, clinician sign-off list | `manifest.json`, `governance_log.md` |

**Sample Pipeline** (simplified, 6 stages): Text extraction → chunking → decision identification → subtree building → tree merging → validation.

### Prompt Bank & Pipeline Builder

All prompts are stored in `prompts.json` and editable live from the UI's **Pipeline Builder** tab. You can:
- Create, edit, and delete prompt templates.
- Compose new pipelines by dragging steps from the prompt bank.
- Switch the active pipeline per upload.

Changes persist to disk immediately — no server restart required.

### Output Schema

Every final artifact conforms to `schema.json`:

```json
{
  "id": "asthma-emergency-triage",
  "version": "1.0.0",
  "name": "Asthma Emergency Triage Protocol",
  "description": "...",
  "root_id": "root",
  "nodes": [
    { "id": "root", "type": "root", "label": "...", ... },
    { "id": "q_fever", "type": "question", "output_map": { "yes": "refer", "no": "monitor" }, ... },
    { "id": "refer", "type": "outcome", ... }
  ],
  "edges": [
    { "source_id": "root", "target_id": "q_fever", "label": "start" }
  ]
}
```

---

## Prerequisites

- **Python 3.9+**
- **Node.js 18+** and npm
- **[Ollama](https://ollama.com/)** installed and running locally with the `deepseek-r1:latest` model

Pull the model before first run:

```bash
ollama pull deepseek-r1:latest
```

---

## Quick Start

### 1. Install Dependencies

```bash
make install
```

This installs Python packages into the local `venv` and runs `npm install` for the frontend.

### 2. Start Ollama

In a separate terminal (if not already running as a service):

```bash
ollama serve
```

### 3. Start the Dev Servers

```bash
make dev
```

This launches both the FastAPI backend (port 4001) and the Vite dev server (port 5173) in parallel.

Open your browser at **http://localhost:5173**

---

## All Make Targets

| Command | Description |
|---------|-------------|
| `make dev` | Start both backend + frontend in parallel **(default)** |
| `make backend` | Start FastAPI backend only on port 4001 |
| `make frontend` | Start Vite dev server only on port 5173 |
| `make install` | Install all Python and Node dependencies |
| `make help` | Show available targets |

---

## Project Structure

```
caire-mvp/
├── Makefile                  # Dev workflow commands
├── requirements.txt          # Python dependencies
├── prompts.json              # Live prompt bank + pipeline recipes
├── schema.json               # JSON schema for output decision trees
│
├── backend/
│   ├── main.py               # FastAPI app — all REST endpoints
│   ├── models.py             # Pydantic models (GraphState, etc.)
│   ├── artifacts/            # Generated JSON decision tree outputs
│   ├── uploads/              # Uploaded PDFs
│   └── pipeline/
│       ├── dynamic_workflow.py   # LangGraph looping graph builder
│       ├── langgraph_workflow.py # Static graph (legacy)
│       ├── ollama_client.py      # HTTP client for local Ollama
│       ├── prompts.py            # Prompt library CRUD + pipeline resolution
│       └── steps/
│           └── nodes.py          # Universal step node (core execution logic)
│
└── frontend/
    ├── src/
    │   └── App.jsx           # React SPA — Upload, Library, Pipeline Builder, Tree Viewer
    └── ...
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI + Uvicorn |
| Orchestration | LangGraph (dynamic looping graph) |
| LLM Engine | Ollama (`deepseek-r1:latest`) via `httpx` |
| Frontend | React + Vite |
| PDF Parsing | `pypdf` |
| State Management | In-memory Python dict (MVP) |
