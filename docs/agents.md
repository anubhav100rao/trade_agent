# Agents

## 1. Orchestrator

**File:** `agents/orchestrator/`

The central coordinator. It does not produce analysis itself — it routes, dispatches, and coordinates other agents.

### `router.py` — Query Classifier

Uses Gemini to parse the user's natural language query and extract:
- `ticker` — primary stock symbol (e.g. `RELIANCE`, `NIFTY`)
- `analysis_type` — `technical | fundamental | sentiment | composite`
- `time_horizon` — `intraday | swing | positional | longterm`

Fallback: if JSON parsing fails, regex extracts uppercase tokens as candidate tickers.

### `state.py` — Shared State

`AnalysisState` TypedDict flows through the entire graph. Each agent node reads what it needs and writes one key back.

### `workflow.py` — Root Graph

Sequential graph: `parse_query → run_technical → run_fundamental → run_sentiment → synthesize`

Supports optional Redis checkpointing when `REDIS_URL` is set.

---

## 2. Technical Analyst

**File:** `agents/technical_analyst/`

Runs a **LangGraph sub-graph** internally: `fetch → compute → interpret → build_result`

### Steps

| Step | What happens |
|---|---|
| **fetch** | Calls `yfinance_fallback.get_ohlcv()` — 60 days of daily candles by default |
| **compute** | Runs the indicator script in the **Python sandbox** |
| **interpret** | Gemini reads the numbers and provides textual analysis |
| **build_result** | Assembles `TechnicalAnalysis` Pydantic model |

### Indicators Computed

| Indicator | Signal logic |
|---|---|
| **RSI (14)** | > 70 → overbought, < 30 → oversold, 40–60 → neutral |
| **MACD** | Histogram direction → bullish/bearish crossover |
| **Bollinger Bands** | `above_upper` → overbought, `below_lower` → oversold |
| **52-week levels** | Price proximity to yearly highs/lows |

### Sandbox

All indicator maths run in `sandbox.py` — a restricted `exec()` environment with:
- `pandas`, `numpy`, `pandas_ta` pre-injected
- `__import__` blocked (no arbitrary imports)
- 3-second timeout via threading

The LLM receives *only* the computed numbers, eliminating hallucination of indicator values.

### System Prompt

`agents/technical_analyst/prompts/system.md` — instructs the LLM to:
- Cite specific RSI/MACD/BB values
- Identify support/resistance levels
- Output a structured BUY/SELL/HOLD/AVOID signal with confidence

---

## 3. Fundamental Analyst

**File:** `agents/fundamental_analyst/workflow.py`

Combines two data sources:

| Source | Data |
|---|---|
| **yfinance** | PE ratio, PB ratio, EPS, dividend yield, market cap, sector |
| **Qdrant RAG** | Chunks from indexed PDFs (annual reports, earnings calls, DRHP) |

Qdrant retrieval is **optional** — if no PDFs have been indexed for the ticker, the analysis proceeds with yfinance metrics only (this is noted in the LLM context).

### Output (`FundamentalAnalysis`)

```
signal:               POSITIVE | NEGATIVE | NEUTRAL
confidence:           0.0 – 1.0
pe_ratio:             float
positive_highlights:  ["Revenue grew 18% YoY", ...]
red_flags:            ["Rising debt-to-equity", ...]
management_sentiment: positive | cautious | negative
sources:              ["AR_FY25.pdf", "yfinance"]
```

---

## 4. Sentiment Watchdog

**File:** `agents/sentiment_watchdog/workflow.py`

Fetches recent news from **MoneyControl** and **Economic Times** RSS feeds, then uses Gemini to score overall sentiment.

### Flow

```
fetch RSS feeds (MoneyControl + ET)
  → filter by ticker keyword and recency (default: last 6 hours)
  → top 15 headlines → Gemini prompt
  → JSON: {score, label, summary, confidence}
```

### Score interpretation

| Score range | Label |
|---|---|
| 0.5 to 1.0 | POSITIVE |
| -0.5 to 0.5 | NEUTRAL |
| -1.0 to -0.5 | NEGATIVE |

If no news is found, returns `score=0.0, label=NEUTRAL, confidence=0.1`.

---

## 5. Risk Assessor

**File:** `agents/risk_assessor/workflow.py`

Pure Python — **no LLM call**. Derives contextual risk flags from technical indicators and sentiment score.

### Risk Flags

| Flag | Trigger |
|---|---|
| `OVERBOUGHT` | RSI > 70 |
| `OVERSOLD` | RSI < 30 |
| `HIGH_VOLATILITY` | BB position `above_upper` or `below_lower`, or sentiment < -0.5 |
| `NEAR_52W_HIGH` | Current price ≥ 98% of 52-week high |
| `NEAR_52W_LOW` | Current price ≤ 102% of 52-week low |
| `STRONG_UPTREND` | Signal = BULLISH and confidence ≥ 0.75 |
| `STRONG_DOWNTREND` | Signal = BEARISH and confidence ≥ 0.75 |

Flags are deduplicated and passed to the Synthesis agent.

---

## 6. Synthesis

**File:** `agents/synthesis/workflow.py`

The final aggregation step. Reads all agent outputs and produces the `Recommendation`.

### Analysis weighting (in the system prompt)

| Query intent | Technical | Fundamental | Sentiment |
|---|---|---|---|
| Intraday / short-term | 60% | 10% | 30% |
| Swing / positional | 40% | 40% | 20% |
| Long-term | 20% | 60% | 20% |

### Output (`Recommendation`)

```json
{
  "ticker":        "RELIANCE",
  "signal":        "BUY",
  "confidence":    0.72,
  "reasoning":     "RSI at 58 (neutral-bullish)...",
  "summary":       "RELIANCE showing bullish technical with positive sentiment",
  "key_metrics":   {"rsi": 58, "macd": "bullish_crossover", "price": 1419.40, "pe": 24.3},
  "risk_flags":    ["NEAR_52W_HIGH"],
  "top_headlines": ["Reliance Q3 beats estimates"],
  "sources":       ["yfinance:RELIANCE.NS", "moneycontrol_rss"],
  "agents_used":   ["technical_analyst", "fundamental_analyst", "sentiment_watchdog", "synthesis"]
}
```
