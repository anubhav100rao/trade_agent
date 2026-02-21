# API Reference

**Base URL:** `http://localhost:8000`  
**Docs UI:** `http://localhost:8000/docs` (Swagger)  
**OpenAPI spec:** `http://localhost:8000/openapi.json`

---

## `GET /health`

Liveness check.

```bash
curl http://localhost:8000/health
```

**Response `200 OK`:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "services": {
    "gemini": "configured",
    "dhan": "fallback_yfinance"
  }
}
```

| `gemini` value | Meaning |
|---|---|
| `configured` | `GEMINI_API_KEY` is set |
| `missing_key` | Key missing — LLM calls will fail |

---

## `POST /analyze`

Main analysis endpoint. Accepts a natural language query, optionally with an explicit ticker.

### Request body

```json
{
  "query":      "Is RELIANCE a good buy today?",
  "ticker":     "RELIANCE",
  "session_id": "optional-uuid-for-multi-turn"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | string | ✅ | Natural language question |
| `ticker` | string | ❌ | If provided, prepended to query to improve routing |
| `session_id` | string | ❌ | Enables Redis-backed session continuity |

### Response `200 OK`

```json
{
  "ticker":        "RELIANCE",
  "query":         "Is RELIANCE a good buy today?",
  "signal":        "BUY",
  "confidence":    0.72,
  "reasoning":     "RSI at 58 suggests neutral-bullish momentum. MACD shows a recent bullish crossover. Positive sentiment with 8 news articles in the last 6 hours. PE of 24.3 is at a slight premium to sector.",
  "summary":       "RELIANCE looks technically bullish with moderate fundamental support",
  "key_metrics": {
    "rsi":             58.4,
    "macd":            "bullish_crossover",
    "price":           1419.4,
    "pe":              24.3,
    "sentiment_score": 0.3
  },
  "risk_flags":    ["NEAR_52W_HIGH"],
  "top_headlines": [
    "Reliance Industries Q3 revenue beats estimates by 4%",
    "RIL Jio subscriber growth continues to impress"
  ],
  "sources":       ["yfinance:RELIANCE.NS", "moneycontrol_rss", "economictimes_rss"],
  "agents_used":   ["technical_analyst", "fundamental_analyst", "sentiment_watchdog", "risk_assessor", "synthesis"],
  "technical_data":   { "rsi": 58.4, "macd_signal": "bullish_crossover", "bb_position": "neutral", ... },
  "fundamental_data": { "signal": "POSITIVE", "pe_ratio": 24.3, "red_flags": [], ... },
  "sentiment_data":   { "score": 0.3, "label": "POSITIVE", "headline_count": 8, ... }
}
```

### Signal values

| Signal | Interpretation |
|---|---|
| `BUY` | Positive bias — multiple dimensions align bullishly |
| `HOLD` | No clear edge — mixed or insufficient signals |
| `SELL` | Negative bias — consider reducing exposure |
| `AVOID` | Strong negative signal — not suitable for entry |

### Risk flag values

| Flag | Meaning |
|---|---|
| `OVERBOUGHT` | RSI > 70 |
| `OVERSOLD` | RSI < 30 |
| `HIGH_VOLATILITY` | Price outside Bollinger Bands |
| `NEAR_52W_HIGH` | Within 2% of 52-week high |
| `NEAR_52W_LOW` | Within 2% of 52-week low |
| `STRONG_UPTREND` | Bullish signal with confidence ≥ 0.75 |
| `STRONG_DOWNTREND` | Bearish signal with confidence ≥ 0.75 |

### Error responses

| Code | When |
|---|---|
| `422 Unprocessable Entity` | Empty/missing query, invalid JSON |
| `500 Internal Server Error` | LLM quota exceeded, yfinance timeout, etc. |

---

## Example queries

```bash
# Technical — RSI, MACD, Bollinger Bands
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"query":"Show technical chart analysis for INFY with RSI and MACD","ticker":"INFY"}'

# Fundamental — PE, earnings, annual report
curl -X POST http://localhost:8000/analyze \
  -d '{"query":"Is HDFCBANK fairly valued based on PE and earnings growth?","ticker":"HDFCBANK"}'

# Sentiment — latest news
curl -X POST http://localhost:8000/analyze \
  -d '{"query":"What is the market sentiment around TATAMOTORS today?","ticker":"TATAMOTORS"}'

# Composite — full analysis
curl -X POST http://localhost:8000/analyze \
  -d '{"query":"Give me a full buy/sell analysis for WIPRO for a 2-week swing trade","ticker":"WIPRO"}'

# Index-level
curl -X POST http://localhost:8000/analyze \
  -d '{"query":"Is NIFTY in a strong uptrend or consolidation phase?"}'
```
