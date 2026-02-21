.PHONY: dev stop run test validate clean

VENV = source /Users/anubhav100rao/python_venv/bin/activate &&

##@ Development Infrastructure

dev:   ## Start Redis, Qdrant, Postgres (docker-compose)
	docker-compose up -d
	@echo "Services started:"
	@echo "  Redis:    localhost:6379  (UI: localhost:8001)"
	@echo "  Qdrant:   localhost:6333"
	@echo "  Postgres: localhost:5432"

stop:  ## Stop all docker services
	docker-compose down

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
