# ============================================================
# Local Genius — Makefile
# ============================================================
# Usage:
#   make setup    — Create venv and install all dependencies
#   make run      — Start the interactive agentic loop
#   make test     — Run the test suite
#   make lint     — Lint the codebase with ruff
#   make clean    — Remove venv, caches, and build artifacts
#   make ollama   — Check Ollama status and pull model
# ============================================================

PYTHON     := python3
VENV       := venv
BIN        := $(VENV)/bin
PIP        := $(BIN)/pip
PYTEST     := $(BIN)/pytest
RUFF       := $(BIN)/ruff
APP        := $(BIN)/python -m src.main

.PHONY: setup run test lint clean ollama help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: $(VENV)/bin/activate ## Create venv and install dependencies

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@cp -n .env.example .env 2>/dev/null || true
	@echo ""
	@echo "✅ Setup complete. Activate with: source $(VENV)/bin/activate"

run: ## Start the interactive agentic loop
	$(APP) --interactive

run-goal: ## Run a single goal (usage: make run-goal GOAL="list files")
	$(APP) --goal "$(GOAL)"

test: ## Run the test suite
	$(PYTEST) -v --tb=short

test-cov: ## Run tests with coverage report
	$(PYTEST) --cov=src --cov-report=term-missing -v

lint: ## Lint the codebase
	$(RUFF) check src/ tests/

lint-fix: ## Lint and auto-fix issues
	$(RUFF) check --fix src/ tests/

clean: ## Remove venv, caches, and build artifacts
	rm -rf $(VENV) __pycache__ .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.py[cod]' -delete 2>/dev/null || true

ollama: ## Check Ollama and pull the configured model
	@echo "Checking Ollama status..."
	@curl -sf http://localhost:11434/api/tags > /dev/null && echo "✅ Ollama is running" || echo "❌ Ollama is not running. Start with: ollama serve"
	@echo "Pulling model (if needed)..."
	ollama pull llama3.2:3b
