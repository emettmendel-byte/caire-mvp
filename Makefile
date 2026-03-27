# ==============================================================================
# Caire MVP — Developer Makefile
# ==============================================================================
# Usage:
#   make dev        — start both frontend and backend (default)
#   make backend    — start FastAPI backend only (port 4001)
#   make frontend   — start Vite dev server only (port 5173)
#   make install    — install all dependencies
#   make help       — show this help

.PHONY: dev backend frontend install help

# Default target
.DEFAULT_GOAL := dev

VENV        := venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
UVICORN     := $(VENV)/bin/uvicorn

CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

## dev: Start both backend and frontend in parallel
dev:
	@echo "$(CYAN)Starting Caire MVP (backend + frontend)...$(RESET)"
	@$(MAKE) -j2 backend frontend

## backend: Start FastAPI backend on port 4001
backend:
	@echo "$(GREEN)[backend]$(RESET) Starting FastAPI on http://localhost:4001"
	@$(UVICORN) backend.main:app --reload --port 4001

## frontend: Start Vite dev server on port 5173
frontend:
	@echo "$(GREEN)[frontend]$(RESET) Starting Vite on http://localhost:5173"
	@cd frontend && npm run dev

## install: Install Python + Node dependencies
install:
	@echo "$(CYAN)Installing Python dependencies...$(RESET)"
	@$(PIP) install -r requirements.txt
	@echo "$(CYAN)Installing Node dependencies...$(RESET)"
	@cd frontend && npm install
	@echo "$(GREEN)All dependencies installed.$(RESET)"

## help: Show available make targets
help:
	@echo ""
	@echo "$(CYAN)Caire MVP — available commands:$(RESET)"
	@grep -E '^## ' Makefile | sed 's/## /  make /' | column -t -s ':'
	@echo ""
