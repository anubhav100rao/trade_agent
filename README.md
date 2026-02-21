# 🏛️ Indian Market Financial Analysis Agent

A **multi-agent decision support system** for Indian equity markets.  
Analyzes stocks and F&O instruments, returns cited recommendations. **No trade execution.**

## Architecture

```
User Query → FastAPI → Orchestrator (LangGraph)
                           ├── Technical Analyst  (RSI / MACD / BB via sandbox)
                           ├── Fundamental Analyst (yfinance + Qdrant RAG)
                           ├── Sentiment Watchdog  (MoneyControl + ET RSS)
                           └── Synthesis → Risk Assessor → Recommendation
```

MCP Servers expose clean tool interfaces to agents:
| Server | Tools |
|--------|-------|
| `nse-fetcher` | `get_ohlc`, `get_stock_info`, `get_option_chain`, `get_market_overview` |
| `fundamental-data` | `search_reports`, `get_financial_summary`, `list_available_reports` |
| `news-radar` | `get_recent_news`, `get_sector_news` |

## Setup

```bash
# 1. Copy and fill in API keys
cp .env.example .env

# Required: your Gemini API key
# GEMINI_API_KEY=... (get free key at https://aistudio.google.com)

# 2. Start infrastructure (Redis, Qdrant, Postgres)
make dev

# 3. Start the API
make run
```

## Usage

```bash
# Health check
curl http://localhost:8000/health

# Analyze a stock
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Is RELIANCE a good buy today?", "ticker": "RELIANCE"}'

# Option chain analysis
curl -X POST http://localhost:8000/analyze \
  -d '{"query": "Show NIFTY option chain analysis for this week expiry"}'
```

### Response shape
```json
{
  "ticker": "RELIANCE",
  "signal": "BUY",
  "confidence": 0.72,
  "reasoning": "RSI at 58 (neutral-bullish zone), MACD shows bullish crossover...",
  "summary": "RELIANCE showing bullish technical setup with positive sentiment",
  "key_metrics": {"rsi": 58, "macd": "bullish_crossover", "price": 1419.40, "pe": 24.3},
  "risk_flags": ["NEAR_52W_HIGH"],
  "top_headlines": ["Reliance Industries Q3 revenue beats estimates..."],
  "agents_used": ["technical_analyst", "fundamental_analyst", "sentiment_watchdog", "synthesis"],
  "sources": ["yfinance:RELIANCE.NS", "moneycontrol_rss"]
}
```

## Ingest Financial Reports (PDF → Qdrant RAG)

```bash
# Index an annual report — enables deep fundamental analysis
python -m ingestion.pdf_pipeline \
  --file /path/to/RELIANCE_AR_FY25.pdf \
  --ticker RELIANCE \
  --report-type annual_report \
  --fiscal-year 2025

# Index recent news (run on a schedule / cron)
python -m ingestion.news_pipeline --tickers RELIANCE INFY TATAMOTORS --hours 6
```

## Project Structure

```
trade_agent/
├── libs/
│   ├── domain_models/          Pydantic: Candle, TechnicalAnalysis, Recommendation, RiskFlag
│   └── llm.py                  Shared Gemini LLM factory
├── mcp_servers/
│   ├── nse_fetcher/            yfinance: OHLCV, option chain, stock info
│   ├── fundamental_data/       Qdrant RAG over financial reports
│   └── news_radar/             MoneyControl + ET RSS scraper
├── agents/
│   ├── orchestrator/           LangGraph root: route → dispatch → synthesize
│   ├── technical_analyst/      RSI/MACD/BB via restricted Python sandbox
│   ├── fundamental_analyst/    yfinance metrics + Qdrant RAG → insight
│   ├── sentiment_watchdog/     News sentiment via Gemini
│   ├── risk_assessor/          Contextual risk flags
│   └── synthesis/              Weighted aggregation → Recommendation
├── ingestion/
│   ├── pdf_pipeline.py         PDF → chunks → Qdrant
│   └── news_pipeline.py        RSS → Qdrant
└── api/
    └── main.py                 FastAPI: GET /health, POST /analyze
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | ✅ | — | Google AI Studio key |
| `GEMINI_MODEL` | ❌ | `gemini-2.0-flash-lite` | Override model |
| `REDIS_URL` | ❌ | — | Enables session checkpointing |
| `QDRANT_URL` | ❌ | in-memory | Qdrant instance for RAG |
| `DATABASE_URL` | ❌ | — | Postgres for audit trails |
