# Testing

The test suite has two layers:

| File | Speed | Needs Gemini? | Needs server? |
|---|---|---|---|
| `tests/test_units.py` | ~15s | ❌ | ❌ |
| `tests/test_api_flows.py` | ~3-5 min | ✅ | ✅ (auto-started) |

---

## Running Tests

```bash
# Fast unit tests only (no API key needed)
pytest tests/test_units.py -v

# Full integration tests (update .env with working Gemini key first)
pytest tests/test_api_flows.py -v

# All tests
pytest tests/ -v

# Skip LLM-dependent tests
pytest tests/ --skip-llm -v
```

---

## `test_units.py` — Fast Unit Tests

Runs in ~15 seconds. No network calls to Gemini. Uses live yfinance.

### Test classes

#### `TestDomainModels`
Validates Pydantic model behaviour.

| Test | What it checks |
|---|---|
| `test_candle_is_bullish` | `close > open` → `is_bullish=True`, `body_size` computed |
| `test_candle_is_bearish` | `close < open` → `is_bullish=False` |
| `test_recommendation_signal_enum` | `TradeSignal.BUY` serialises to `"BUY"` |
| `test_recommendation_confidence_clamp` | Pydantic rejects `confidence > 1.0` |
| `test_risk_flag_values` | All expected flags present in enum |

#### `TestYfinanceWrapper`
Validates the `yfinance_fallback` module (live network calls to Yahoo Finance).

| Test | What it checks |
|---|---|
| `test_symbol_conversion_equity` | `RELIANCE` → `RELIANCE.NS` |
| `test_symbol_conversion_index` | `NIFTY` → `^NSEI`, `BANKNIFTY` → `^NSEBANK` |
| `test_symbol_no_double_suffix` | `RELIANCE.NS` → `RELIANCE.NS` (no double suffix) |
| `test_get_ohlcv_returns_list` | Returns non-empty candle list |
| `test_ohlcv_ohlc_relationship` | `high ≥ close ≥ low` invariant for all candles |

#### `TestSandbox`
Validates the restricted Python execution environment.

| Test | What it checks |
|---|---|
| `test_rsi_result` | RSI computed and in 0–100 range |
| `test_bollinger_bands` | BBU > BBL using correct column name lookup |
| `test_import_blocked` | `import subprocess` raises `SandboxError` |
| `test_timeout_enforced` | Infinite loop raises `SandboxTimeout` within 0.5s |
| `test_result_must_be_dict` | Non-dict `result` raises `SandboxError` |

#### `TestQdrantStoreFallback`
Tests the pure Python list-based fallback (no Qdrant server).

| Test | What it checks |
|---|---|
| `test_upsert_and_retrieve` | Chunk indexed and returned in search |
| `test_ticker_isolation` | RELIANCE search does not return WIPRO chunks |

#### `TestRSSScraper`
Tests RSS feed fetching (live network to MoneyControl/ET).

| Test | What it checks |
|---|---|
| `test_moneycontrol_fetch_no_crash` | No exception, returns list |
| `test_et_fetch_no_crash` | No exception, returns list |
| `test_articles_have_required_fields` | Each article has `title` and `source` |

#### `TestRiskAssessor`
Tests risk flag derivation logic.

| Test | Flag tested |
|---|---|
| `test_overbought_rsi` | RSI 78 → `OVERBOUGHT` |
| `test_oversold_rsi` | RSI 25 → `OVERSOLD` |
| `test_near_52w_high` | Price ≥ 98% of high → `NEAR_52W_HIGH` |
| `test_high_volatility_from_bb` | `bb_position=above_upper` → `HIGH_VOLATILITY` |
| `test_no_flags_when_neutral` | RSI 55, neutral signal → no RSI flags |
| `test_strong_uptrend` | BULLISH with confidence 0.82 → `STRONG_UPTREND` |

---

## `test_api_flows.py` — Server Integration Tests

Spins the **real FastAPI server** on port 8765 using `subprocess`, then hits it with `httpx`. Requires a working `GEMINI_API_KEY` in `.env`. Each `TestFlow` class shares a fixture that caches the response so the LLM is called **once per class**, not once per test.

### Test classes

#### `TestHealthFlow`
| Test | Assertion |
|---|---|
| `test_health_status_ok` | `status == "ok"` |
| `test_health_reports_version` | `version` is semver x.y.z |
| `test_health_reports_gemini_service` | `services.gemini` in `(configured, missing_key)` |
| `test_docs_accessible` | `/docs` returns 200 |
| `test_openapi_schema` | `/analyze` and `/health` in schema paths |

#### `TestRouterFlow` *(unit — no server needed)*
Tests `classify_query()` LLM call directly.

| Test | Query | Expected ticker |
|---|---|---|
| `test_classify_technical_query` | "Show RSI and MACD for RELIANCE" | RELIANCE |
| `test_classify_fundamental_query` | "PE ratio of TATAMOTORS" | TATAMOTORS |
| `test_classify_sentiment_query` | "Latest news about INFY" | INFY |
| `test_classify_defaults_to_nifty_when_no_ticker` | "Is market bullish?" | any non-empty string |
| `test_ticker_uppercase` | "buy or sell reliance" | uppercase |

#### `TestTechnicalFlow`
Sends: `"Show technical analysis for INFY with RSI and MACD"`

| Test | Asserts |
|---|---|
| `test_has_signal` | `signal` in `(BUY, SELL, HOLD, AVOID)` |
| `test_has_confidence` | `0.0 ≤ confidence ≤ 1.0` |
| `test_technical_agent_ran` | `"technical_analyst"` in `agents_used` |
| `test_rsi_in_key_metrics` | `rsi` present and in 0–100 |
| `test_price_in_key_metrics` | `price > 0` |
| `test_source_includes_yfinance` | `sources` has `yfinance:*` entry |
| `test_technical_data_has_indicator_detail` | `rsi`, `macd_signal`, or `bb_position` present |

#### `TestFundamentalFlow`
Sends: `"Financial health and valuation of HDFCBANK?"`

| Test | Asserts |
|---|---|
| `test_fundamental_agent_ran` | `"fundamental_analyst"` in `agents_used` |
| `test_has_ticker` | `ticker == "HDFCBANK"` |
| `test_fundamental_data_present` | `fundamental_data` is not None |
| `test_pe_ratio_present_in_fundamental_data` | `pe_ratio` key exists |
| `test_signal_and_summary_present` | valid signal, summary ≥ 5 chars |

#### `TestSentimentFlow`
Sends: `"Market sentiment around TATAMOTORS?"`

| Test | Asserts |
|---|---|
| `test_sentiment_agent_ran` | `"sentiment_watchdog"` in `agents_used` |
| `test_sentiment_data_structure` | `score`, `label`, `headline_count` present |
| `test_sentiment_score_in_range` | `-1.0 ≤ score ≤ 1.0` |
| `test_sentiment_label_valid` | label in `(POSITIVE, NEGATIVE, NEUTRAL)` |
| `test_top_headlines_is_list` | `top_headlines` is a list |

#### `TestCompositeFlow`
Sends: `"Full buy/sell analysis for RELIANCE"`

| Test | Asserts |
|---|---|
| `test_all_agents_ran` | technical, fundamental, sentiment, synthesis all in `agents_used` |
| `test_recommendation_shape` | All required fields present |
| `test_reasoning_is_non_trivial` | `reasoning` ≥ 30 chars |
| `test_risk_assessor_output` | `risk_flags` is a list |
| `test_ticker_matches_request` | `ticker == "RELIANCE"` |
| `test_key_metrics_non_empty` | `key_metrics` has ≥ 1 entry |

#### `TestNSEFetcherTools` *(unit — live yfinance)*
Direct tests of `yfinance_fallback` functions.

#### `TestQdrantStore` *(unit — list fallback)*
Tests upsert, cross-ticker isolation, `list_reports`.

#### `TestErrorHandling`
| Test | Input | Expected |
|---|---|---|
| `test_empty_query_returns_422` | `{"query": ""}` | 422 |
| `test_missing_query_field_returns_422` | `{"ticker": "RELIANCE"}` | 422 |
| `test_whitespace_only_query_returns_422` | `{"query": "   "}` | 422 |
| `test_invalid_json_returns_422` | `"not json"` | 422 |
| `test_response_is_json` | `/health` | `content-type: application/json` |

#### `TestSandboxSafety`
Tests security and timeout within the integration server context.
