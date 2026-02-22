.PHONY: dev stop run run-nse-mcp test validate clean help

VENV = source /Users/anubhav100rao/python_venv/bin/activate &&

##@ Development Infrastructure

PID_FILE := .api.pid

dev:   ## Start infra (Docker) + FastAPI server in background
	docker-compose up -d
	@echo "Infrastructure started:"
	@echo "  Redis:    localhost:6379"
	@echo "  Qdrant:   localhost:6333"
	@echo "  Postgres: localhost:5432"
	@echo ""
	$(VENV) uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info & echo $$! > $(PID_FILE)
	@sleep 1
	@echo "API server started — http://localhost:8000  (PID: $$(cat $(PID_FILE)))"
	@echo "Run 'make logs' for infra logs, 'make stop' to stop everything."

stop:  ## Stop API server + all Docker services
	@if [ -f $(PID_FILE) ]; then \
		PID=$$(cat $(PID_FILE)); \
		echo "Stopping API server (PID: $$PID)..."; \
		kill $$PID 2>/dev/null || true; \
		rm -f $(PID_FILE); \
	else \
		echo "No PID file found — killing any uvicorn process on :8000..."; \
		lsof -ti:8000 | xargs kill -9 2>/dev/null || true; \
	fi
	docker-compose down
	@echo "All services stopped."

logs:  ## Tail docker-compose logs
	docker-compose logs -f

##@ Application

run:   ## Start the FastAPI gateway on :8000
	$(VENV) uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

run-nse-mcp:  ## Start the nse-fetcher MCP server
	$(VENV) python -m mcp_servers.nse_fetcher.server

##@ Testing

test:  ## Run sandbox validation tests
	$(VENV) python sandbox_test.py

validate:  ## Run validation then hit the live API
	$(VENV) python sandbox_test.py
	@echo "\n--- Smoke testing live API ---"
	curl -s http://localhost:8000/health | python3 -m json.tool
	curl -s -X POST http://localhost:8000/analyze \
		-H "Content-Type: application/json" \
		-d '{"query":"Is RELIANCE a good buy today?","ticker":"RELIANCE"}' \
		| python3 -m json.tool

##@ Utilities

clean:  ## Remove __pycache__ dirs
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
