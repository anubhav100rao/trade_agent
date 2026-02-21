# Documentation

Welcome to the **Indian Market Financial Analysis Agent** — a multi-agent decision support system for NSE/BSE markets.

## Contents

| Document | Description |
|---|---|
| [Architecture](./architecture.md) | High-level system design, agent graph, data flow |
| [Agents](./agents.md) | Each agent — purpose, inputs, outputs, design decisions |
| [MCP Servers](./mcp_servers.md) | Tool interfaces for data fetching and RAG |
| [API Reference](./api.md) | FastAPI endpoints, request/response schemas, examples |
| [Ingestion Pipelines](./ingestion.md) | Indexing PDFs and news into Qdrant |
| [Configuration](./configuration.md) | Environment variables, infrastructure setup |
| [Testing](./testing.md) | Running tests, what each test class covers |

## Quick Start

```bash
cp .env.example .env          # add your GEMINI_API_KEY
make dev                       # start Redis + Qdrant + Postgres
make run                       # start API on :8000
curl http://localhost:8000/health
```

## Key Design Principles

- **No trade execution** — pure decision support (DSS)
- **Cited recommendations** — every output links to its data source
- **Graceful degradation** — all infra dependencies are optional (Qdrant → list, Redis → stateless)
- **LLM math sandbox** — indicator maths run in a restricted Python exec, not in the LLM
