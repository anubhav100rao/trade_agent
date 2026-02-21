# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        User / Client                            │
└──────────────────────────────┬──────────────────────────────────┘
                               │ POST /analyze
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Gateway (:8000)                     │
│  GET /health                POST /analyze                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              Orchestrator (LangGraph root graph)                │
│                                                                 │
│  parse_query ──► run_technical ──► run_fundamental             │
│                                         │                       │
│                               run_sentiment                     │
│                                         │                       │
│                                    synthesize                   │
│                                    + risk_assessor              │
└─────────────────────────────────────────────────────────────────┘
         │                │                   │
         ▼                ▼                   ▼
  ┌─────────────┐  ┌─────────────┐   ┌─────────────┐
  │  Technical  │  │ Fundamental │   │  Sentiment  │
  │  Analyst    │  │  Analyst    │   │  Watchdog   │
  │             │  │             │   │             │
  │ yfinance    │  │ yfinance +  │   │ MC + ET RSS │
  │ + sandbox   │  │ Qdrant RAG  │   │ + Gemini    │
  └─────────────┘  └─────────────┘   └─────────────┘
```

## Agent Graph (LangGraph)

The Orchestrator is a **sequential LangGraph graph**. All agents run for every query — this ensures a holistic synthesis regardless of query intent.

```
parse_query → run_technical → run_fundamental → run_sentiment → synthesize → END
```

### Node descriptions

| Node | Function | Failure mode |
|---|---|---|
| `parse_query` | Gemini extracts ticker + classifies `analysis_type` | Falls back to `NIFTY / composite` |
| `run_technical` | Technical Analyst sub-graph | Sets `technical_result = None`, adds error note |
| `run_fundamental` | Fundamental Analyst | Sets `fundamental_result = None`, continues |
| `run_sentiment` | Sentiment Watchdog | Sets `sentiment_result = None` (0 news = NEUTRAL) |
| `synthesize` | Risk Assessor + Synthesis → Recommendation | Always returns a dict |

## Shared State (`AnalysisState`)

```python
class AnalysisState(TypedDict):
    user_query:           str
    session_id:           str
    ticker:               str
    analysis_type:        Literal["technical", "fundamental", "sentiment", "composite"]
    technical_result:     Optional[dict]
    fundamental_result:   Optional[dict]
    sentiment_result:     Optional[dict]
    final_recommendation: Optional[dict]
    error:                Optional[str]
```

## Data Flow

```
User Query
  │
  ├─ Gemini (router)    → ticker="RELIANCE", analysis_type="composite"
  │
  ├─ yfinance           → 60 days of OHLCV candles
  │
  ├─ Python sandbox     → RSI=58, MACD=bullish, BB=neutral
  │
  ├─ Gemini (TA)        → TechnicalAnalysis(signal=BULLISH, confidence=0.71)
  │
  ├─ yfinance           → PE=24.3, 52w_high=1480, sector=Energy
  │
  ├─ Qdrant RAG         → 3 chunks from annual report (if indexed)
  │
  ├─ Gemini (FA)        → FundamentalAnalysis(signal=POSITIVE)
  │
  ├─ MoneyControl RSS   → 8 headlines in last 6h
  │
  ├─ Gemini (SA)        → SentimentAnalysis(score=0.3, label=POSITIVE)
  │
  ├─ Risk Assessor      → [NEAR_52W_HIGH]
  │
  └─ Gemini (synthesis) → Recommendation(signal=BUY, confidence=0.68)
```

## Infrastructure

| Service | Role | Required? |
|---|---|---|
| **Gemini API** | LLM for routing, analysis, synthesis | ✅ Yes |
| **yfinance** | Market data (OHLCV, fundamentals, options) | ✅ Yes (built-in) |
| **Qdrant** | Vector store for PDF / news RAG | ❌ Optional |
| **Redis** | LangGraph session checkpointing | ❌ Optional |
| **Postgres** | Audit trail / future trade log | ❌ Optional |

When optional services are absent, the system degrades gracefully rather than failing.

## LLM Sandbox (Key Design)

All numerical indicator calculations are executed in a **restricted Python exec environment**, not in the LLM prompt. This eliminates LLM hallucination of indicator values.

```
┌─────────────────────────────────────────────┐
│            Sandbox Environment              │
│                                             │
│  Pre-injected:  pd, np, ta (pandas-ta)      │
│  Pre-built:     open, high, low, close      │
│                 (as pd.Series)              │
│  Blocked:       __import__, os, sys, ...    │
│  Timeout:       3 seconds (configurable)    │
└─────────────────────────────────────────────┘
```

Indicator scripts produce a `result` dict; the LLM only **interprets** the numbers.

## Session Checkpointing

When `REDIS_URL` is set, LangGraph uses `RedisSaver` to checkpoint state per `session_id`. This enables multi-turn conversations where a follow-up query like "what about INFY?" can inherit context from the prior exchange.
