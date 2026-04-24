# ═══════════════════════════════════════════════════════════════
# Business Automation Platform — Makefile
# Run common tasks with: make <target>
# ═══════════════════════════════════════════════════════════════

PYTHON = python3
VENV = venv
PIP = pip
PY = python

.PHONY: help setup install server test logs stop clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Full setup: create venv, install deps
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install: ## Install/update dependencies
	$(PIP) install -r requirements.txt

server: ## Start the Azure Functions server (port 8000)
	PATH=$(CURDIR)/venv/bin:$(PATH) CLAUDECODE=1 func start --port 8000

test: ## Run unit tests (no server needed)
	$(PY) -m pytest tests/ -v

logs: ## Tail the server log
	tail -50 server.log

stop: ## Stop the server
	@pkill -f "func start" 2>/dev/null && echo "Server stopped" || echo "No server running"

clean: ## Remove caches and temp files
	find . -type d -name __pycache__ -not -path './venv/*' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache tests/.pytest_cache server.log
