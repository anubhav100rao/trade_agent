# Configuration

## Environment Variables

Copy `.env.example` to `.env` and fill in the values.

```bash
cp .env.example .env
```

### Required

| Variable | Description | How to get |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key for all LLM calls | [aistudio.google.com](https://aistudio.google.com) → API Keys |

### Optional — LLM

| Variable | Default | Description |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.0-flash-lite` | Override model. Available models for your key: `gemini-2.0-flash-lite`, `gemini-2.0-flash`, `gemini-2.5-flash` |

### Optional — Infrastructure

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | *(not set)* | `redis://localhost:6379` — enables LangGraph session checkpointing |
| `QDRANT_URL` | *(not set)* | `http://localhost:6333` — enables vector search for RAG |
| `DATABASE_URL` | *(not set)* | PostgreSQL — reserved for future audit trail |

### Optional — API Server

| Variable | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Listen port |

---

## Local Development Setup

### 1. Python environment

```bash
python3 -m venv venv
source venv/bin/activate           # macOS/Linux
pip install -e ".[dev]"            # installs all deps from pyproject.toml
```

### 2. Infrastructure (Docker)

```bash
make dev       # starts Redis + Qdrant + Postgres via docker-compose
make stop      # stop all services
make logs      # tail service logs
```

Services started:

| Service | Port | Used for |
|---|---|---|
| Redis | 6379 | LangGraph session checkpointing |
| Qdrant | 6333 | RAG vector search, web UI at :6334 |
| Postgres | 5432 | Future audit trails |

### 3. Start the API

```bash
make run       # uvicorn api.main:app --reload
# or
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Production Deployment

### Environment considerations

- Set `GEMINI_API_KEY` via a secrets manager (AWS Secrets Manager, GCP Secret Manager)
- Set `REDIS_URL` to a managed Redis (ElastiCache, Memorystore, Upstash)
- Set `QDRANT_URL` to a managed Qdrant (Qdrant Cloud) or self-hosted
- Use `GEMINI_MODEL=gemini-2.0-flash` for higher throughput if budget allows

### Docker (single container)

```dockerfile
# Build
docker build -t trade-agent .

# Run
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=... \
  -e REDIS_URL=redis://your-redis:6379 \
  -e QDRANT_URL=http://your-qdrant:6333 \
  trade-agent
```

### Health check

```bash
curl http://your-host:8000/health
# Expected: {"status":"ok","version":"0.1.0"}
```

---

## Makefile Targets

| Target | Command | Description |
|---|---|---|
| `make dev` | `docker-compose up -d` | Start local infrastructure |
| `make stop` | `docker-compose down` | Stop infrastructure |
| `make logs` | `docker-compose logs -f` | Tail infra logs |
| `make run` | `uvicorn api.main:app --reload` | Start API server |
| `make test` | `pytest tests/` | Run all tests |
| `make clean` | removes `*.pyc`, caches | Clean up |
| `make help` | lists targets | Show help |

---

## Qdrant Collections

The platform uses a single collection: `financial_reports`

| Field | Type | Description |
|---|---|---|
| `text` | string | Chunk text content |
| `ticker` | string | NSE symbol (indexed for filtering) |
| `report_type` | string | `annual_report`, `quarterly_results`, `earnings_call`, `drhp`, `news` |
| `fiscal_year` | int | Optional year for filtering |
| `source_file` | string | Original filename |
| `page` | int | Page number in original document |
