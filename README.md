# Caire Medical Guideline Parser

This is a minimal, production-ready web application that lets a user upload a clinical guideline PDF and runs a LangGraph-based multi-step pipeline using a local Ollama model to output a JSON decision tree.

## Prerequisites
- Python 3.9+
- [Ollama](https://ollama.com/) installed and running locally.

## Setup Instructions

1. **Start Ollama**
   Ensure Ollama is running and has downloaded the `deepseek-r1:latest` model.
   ```bash
   ollama serve
   ```
   In a separate terminal:
   ```bash
   ollama pull deepseek-r1:latest
   ```

2. **Install Dependencies**
   It's recommended to use a virtual environment.
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Run the Application & Frontend**
   Start the FastAPI development server:
   ```bash
   uvicorn backend.main:app --reload --port 4001
   ```
   In a separate terminal, start the React Vite server:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Access the Web UI**
   Open your browser and navigate to:
   http://localhost:5173

## Architecture

- **Backend**: FastAPI, hosting REST endpoints (`/api/upload`, `/api/prompts`, `/api/status`, `/api/library`).
- **Orchestration**: LangGraph orchestrates a 6-step prompt pipeline acting as distinct agents analyzing the extracted text.
- **Frontend**: A React Single Page Application (Vite), featuring Library views and a flowchart-like Tree Viewer.
- **LLM Engine**: Local Ollama via HTTP request (`httpx`). All prompts strictly enforce JSON formatting for stable tree parsing.
