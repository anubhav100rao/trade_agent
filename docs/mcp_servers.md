# MCP Servers

MCP (Model Context Protocol) servers expose **tool interfaces** to agents. All servers are built with [FastMCP](https://github.com/jlowin/fastmcp).

---

## `nse-fetcher`

**File:** `mcp_servers/nse_fetcher/server.py`  
**Data source:** Yahoo Finance (`yfinance` library)

Provides live and historical market data for NSE/BSE instruments.

### Symbol conventions

| Input | Resolved to |
|---|---|
| `RELIANCE` | `RELIANCE.NS` |
| `NIFTY` | `^NSEI` |
| `BANKNIFTY` | `^NSEBANK` |
| `SENSEX` | `^BSESN` |
| `RELIANCE.NS` | `RELIANCE.NS` (unchanged) |

### Tools

#### `get_ohlc(symbol, interval, days)`

Fetch historical OHLCV candles.

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `symbol` | str | — | NSE ticker e.g. `RELIANCE` |
| `interval` | str | `1d` | `1m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1w` |
| `days` | int | `60` | Calendar days of history (intraday capped at 59) |

**Returns:**
```json
{
  "symbol": "RELIANCE",
  "interval": "1d",
  "candles": [
    {"ticker": "RELIANCE", "timestamp": "2025-01-15T00:00:00", "open": 1390.0,
     "high": 1425.5, "low": 1385.0, "close": 1419.4, "volume": 8500000}
  ],
  "count": 43,
  "source": "yfinance"
}
```

#### `get_stock_info(symbol)`

Fundamentals + price snapshot.

**Returns:**
```json
{
  "current_price": 1419.4,
  "52w_high": 1480.0,
  "52w_low": 1185.0,
  "pe_ratio": 24.3,
  "pb_ratio": 2.1,
  "eps": 58.4,
  "market_cap": 19200000000000,
  "dividend_yield": 0.003,
  "sector": "Energy",
  "industry": "Oil & Gas Refining",
  "source": "yfinance"
}
```

#### `get_option_chain(symbol)`

Near-ATM options for the nearest expiry.

**Returns:**
```json
{
  "symbol": "RELIANCE",
  "expiries": ["2025-02-27", "2025-03-27"],
  "nearest_expiry": "2025-02-27",
  "put_call_ratio": 0.87,
  "calls_near_atm": [{"strike": 1420, "lastPrice": 15.5, "openInterest": 12000, "impliedVolatility": 0.18}],
  "puts_near_atm":  [{"strike": 1400, "lastPrice": 12.0, "openInterest": 8500, "impliedVolatility": 0.17}]
}
```

#### `get_market_overview()`

**Returns:**
```json
{
  "nifty_50": 22450.3,
  "banknifty": 47800.6,
  "source": "yfinance"
}
```

---

## `fundamental-data`

**File:** `mcp_servers/fundamental_data/server.py`  
**Data source:** Qdrant vector store + yfinance

Searches indexed financial reports (annual reports, earnings calls, DRHP) using **semantic search**.

### Tools

#### `search_reports(ticker, query, fiscal_year?)`

Semantic search over indexed PDF chunks.

| Parameter | Type | Required |
|---|---|---|
| `ticker` | str | ✅ |
| `query` | str | ✅ e.g. `"revenue growth Q3 FY25"` |
| `fiscal_year` | int | ❌ e.g. `2025` for filtering |

**Returns:** List of matching text chunks with relevance scores.

```json
{
  "ticker": "RELIANCE",
  "results": [
    {"text": "Revenue grew 18% YoY to ₹2.3L crore...", "score": 0.91,
     "report_type": "annual_report", "fiscal_year": 2025, "page": 42}
  ],
  "count": 3,
  "source": "qdrant"
}
```

#### `get_financial_summary(ticker)`

Always-available yfinance financial snapshot (no indexing required).

#### `list_available_reports(ticker)`

Lists all PDFs indexed in Qdrant for a ticker.

### Qdrant Store Degradation

| Condition | Behavior |
|---|---|
| `QDRANT_URL` set + Qdrant running | Full vector search with sentence-transformers embeddings |
| `QDRANT_URL` not set | Pure Python list fallback (keyword search) |
| `qdrant-client` not installed | Pure Python list fallback |

---

## `news-radar`

**File:** `mcp_servers/news_radar/server.py`  
**Data source:** MoneyControl RSS + Economic Times RSS

### RSS Feeds polled

| Source | Feeds |
|---|---|
| MoneyControl | business, market_reports, results |
| Economic Times | markets/stocks, markets |

### Tools

#### `get_recent_news(ticker, hours_back)`

Fetch and filter articles mentioning `ticker` in the last `hours_back` hours.

| Parameter | Default |
|---|---|
| `ticker` | — |
| `hours_back` | `6` |

**Returns:**
```json
{
  "ticker": "INFY",
  "articles": [
    {"title": "Infosys raises FY25 revenue guidance...",
     "summary": "...", "url": "https://...", "published_at": "2025-01-15T10:30:00+00:00",
     "source": "economictimes"}
  ],
  "count": 8,
  "hours_back": 6
}
```

#### `get_sector_news(sector, hours_back)`

Broader market/sector news. `sector` examples: `"banking"`, `"IT"`, `"pharma"`, `"market"`.
