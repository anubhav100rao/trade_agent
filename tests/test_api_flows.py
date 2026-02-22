"""
Integration tests for the Indian Market Financial Analysis Agent.

Strategy:
  - Spin up the real FastAPI server via subprocess in a session-scoped fixture
  - Use httpx to call live endpoints
  - Assert on FLOW-SPECIFIC indicators, not the full response shape
  - Each test class maps to one application flow

Flows covered:
  1. Health / System        — server is up, services are reported
  2. Router / Query parsing — ticker extraction + analysis_type classification
  3. Technical flow         — RSI/MACD/BB indicators present in result
  4. Fundamental flow       — PE ratio, sector, fundamental_data present
  5. Sentiment flow         — sentiment_data, score range, headline_count
  6. Composite flow         — all agents ran, recommendation has signal + confidence
  7. NSE-fetcher tools      — OHLC candles, stock info, option chain structure
  8. Qdrant store (unit)    — upsert + search without network
  9. Error handling         — empty query 422, oversized query handled
  10. Sandbox safety        — arbitrary __import__ blocked, timeout enforced
"""
import os
import sys
import time
import subprocess
import signal
import pytest
import httpx
import warnings
warnings.filterwarnings("ignore")

# Force tests to use mock LLM to avoid quota limits
os.environ["MOCK_LLM"] = "true"

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

API_BASE = "http://localhost:8765"   # isolated port, won't clash with dev server
STARTUP_TIMEOUT = 15                 # seconds to wait for server to be ready
REQUEST_TIMEOUT = 120.0              # Gemini LLM calls can be slow


# ══════════════════════════════════════════════════════════════════════════
# Server lifecycle fixture
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def server():
    """
    Start the FastAPI server in a subprocess for the whole test session.
    Yields the base URL, then tears down.
    """
    venv_python = os.path.join(
        os.path.expanduser("~"), "python_venv", "bin", "python"
    )
    proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", "8765", "--log-level", "warning"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONPATH": ROOT, "MOCK_LLM": "true"},
    )

    # Wait until the health endpoint responds
    client = httpx.Client(base_url=API_BASE, timeout=5.0)
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            r = client.get("/health")
            if r.status_code == 200:
                break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("Server did not start within timeout")

    yield API_BASE

    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def client(server):
    """Shared httpx client for the session."""
    with httpx.Client(base_url=server, timeout=REQUEST_TIMEOUT) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════
# 1. Health / System Flow
# ══════════════════════════════════════════════════════════════════════════

class TestHealthFlow:
    """Server is up and reports its service status correctly."""

    def test_health_status_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_health_reports_version(self, client):
        data = client.get("/health").json()
        assert "version" in data
        assert data["version"].count(".") == 2   # semver x.y.z

    def test_health_reports_gemini_service(self, client):
        data = client.get("/health").json()
        services = data.get("services", {})
        assert "gemini" in services
        # Either 'configured' or 'missing_key' — key must be present
        assert services["gemini"] in ("configured", "missing_key")

    def test_docs_accessible(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_openapi_schema(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "/analyze" in schema["paths"]
        assert "/health" in schema["paths"]


# ══════════════════════════════════════════════════════════════════════════
# 2. Router / Query Parsing Flow (unit-level, no LLM needed)
# ══════════════════════════════════════════════════════════════════════════

class TestRouterFlow:
    """Ticker extraction and analysis_type classification."""

    def test_classify_technical_query(self):
        from agents.orchestrator.router import classify_query
        result = classify_query("Show me the RSI and MACD for RELIANCE")
        assert result["ticker"] == "RELIANCE"
        assert result["analysis_type"] in ("technical", "composite")

    def test_classify_fundamental_query(self):
        from agents.orchestrator.router import classify_query
        result = classify_query("What is the PE ratio and debt of TATAMOTORS for FY25?")
        assert result["ticker"] == "TATAMOTORS"
        assert result["analysis_type"] in ("fundamental", "composite")

    def test_classify_sentiment_query(self):
        from agents.orchestrator.router import classify_query
        result = classify_query("What is the latest news about INFY?")
        assert result["ticker"] == "INFY"
        assert result["analysis_type"] in ("sentiment", "composite")

    def test_classify_defaults_to_nifty_when_no_ticker(self):
        from agents.orchestrator.router import classify_query
        result = classify_query("Is the market bullish today?")
        # Should not crash; ticker must be a non-empty string
        assert isinstance(result["ticker"], str) and len(result["ticker"]) >= 2

    def test_ticker_uppercase(self):
        from agents.orchestrator.router import classify_query
        result = classify_query("Buy or sell reliance shares?")
        assert result["ticker"] == result["ticker"].upper()


# ══════════════════════════════════════════════════════════════════════════
# 3. Technical Flow
# ══════════════════════════════════════════════════════════════════════════

class TestTechnicalFlow:
    """Technical Analyst runs, indicator keys are present in response."""

    @pytest.fixture(scope="class")
    def response(self, client):
        r = client.post("/analyze", json={
            "query": "Show me the technical analysis for INFY with RSI and MACD",
            "ticker": "INFY",
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_has_signal(self, response):
        assert response["signal"] in ("BUY", "SELL", "HOLD", "AVOID")

    def test_has_confidence(self, response):
        conf = response["confidence"]
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0

    def test_technical_agent_ran(self, response):
        assert "technical_analyst" in response.get("agents_used", [])

    def test_rsi_in_key_metrics(self, response):
        metrics = response.get("key_metrics", {})
        assert "rsi" in metrics, f"RSI missing from key_metrics: {metrics}"
        rsi = metrics["rsi"]
        assert isinstance(rsi, (int, float))
        assert 0 <= rsi <= 100, f"RSI out of range: {rsi}"

    def test_price_in_key_metrics(self, response):
        metrics = response.get("key_metrics", {})
        assert "price" in metrics
        assert metrics["price"] > 0

    def test_source_includes_yfinance(self, response):
        sources = response.get("sources", [])
        assert any("yfinance" in s for s in sources), f"yfinance source missing: {sources}"

    def test_technical_data_has_indicator_detail(self, response):
        td = response.get("technical_data") or {}
        # At least one of these deep indicator fields must be present
        indicator_keys = {"rsi", "macd_signal", "bb_position"}
        present = indicator_keys & set(td.keys())
        assert present, f"No indicator keys found in technical_data: {list(td.keys())}"


# ══════════════════════════════════════════════════════════════════════════
# 4. Fundamental Flow
# ══════════════════════════════════════════════════════════════════════════

class TestFundamentalFlow:
    """Fundamental Analyst runs and returns financial metrics."""

    @pytest.fixture(scope="class")
    def response(self, client):
        r = client.post("/analyze", json={
            "query": "What is the valuation and financial health of HDFCBANK?",
            "ticker": "HDFCBANK",
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_fundamental_agent_ran(self, response):
        assert "fundamental_analyst" in response.get("agents_used", [])

    def test_has_ticker(self, response):
        assert response.get("ticker") == "HDFCBANK"

    def test_fundamental_data_present(self, response):
        assert response.get("fundamental_data") is not None

    def test_pe_ratio_present_in_fundamental_data(self, response):
        fd = response.get("fundamental_data") or {}
        # pe_ratio may be None for some stocks but the key must exist
        assert "pe_ratio" in fd, f"pe_ratio key missing from fundamental_data: {list(fd.keys())}"

    def test_signal_and_summary_present(self, response):
        assert response.get("signal") in ("BUY", "SELL", "HOLD", "AVOID")
        assert isinstance(response.get("summary"), str)
        assert len(response.get("summary", "")) > 5


# ══════════════════════════════════════════════════════════════════════════
# 5. Sentiment Flow
# ══════════════════════════════════════════════════════════════════════════

class TestSentimentFlow:
    """Sentiment Watchdog runs; sentiment_data has expected structure."""

    @pytest.fixture(scope="class")
    def response(self, client):
        r = client.post("/analyze", json={
            "query": "What is the market sentiment and latest news around TATAMOTORS?",
            "ticker": "TATAMOTORS",
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_sentiment_agent_ran(self, response):
        assert "sentiment_watchdog" in response.get("agents_used", [])

    def test_sentiment_data_structure(self, response):
        sd = response.get("sentiment_data")
        assert sd is not None
        assert "score" in sd
        assert "label" in sd
        assert "headline_count" in sd

    def test_sentiment_score_in_range(self, response):
        score = response["sentiment_data"]["score"]
        assert -1.0 <= score <= 1.0, f"Score out of [-1, 1]: {score}"

    def test_sentiment_label_valid(self, response):
        label = response["sentiment_data"]["label"]
        assert label in ("POSITIVE", "NEGATIVE", "NEUTRAL")

    def test_top_headlines_is_list(self, response):
        headlines = response.get("top_headlines", [])
        assert isinstance(headlines, list)


# ══════════════════════════════════════════════════════════════════════════
# 6. Composite Flow — all agents
# ══════════════════════════════════════════════════════════════════════════

class TestCompositeFlow:
    """Full pipeline: all four agents run and produce a coherent output."""

    @pytest.fixture(scope="class")
    def response(self, client):
        r = client.post("/analyze", json={
            "query": "Is RELIANCE a good buy today? Give me a full analysis.",
            "ticker": "RELIANCE",
        })
        assert r.status_code == 200, r.text
        return r.json()

    def test_all_agents_ran(self, response):
        agents = set(response.get("agents_used", []))
        assert "technical_analyst" in agents
        assert "fundamental_analyst" in agents
        assert "sentiment_watchdog" in agents
        assert "synthesis" in agents

    def test_recommendation_shape(self, response):
        required = {"ticker", "signal", "confidence", "reasoning", "summary",
                    "key_metrics", "risk_flags", "agents_used", "sources"}
        missing = required - set(response.keys())
        assert not missing, f"Missing recommendation fields: {missing}"

    def test_reasoning_is_non_trivial(self, response):
        reasoning = response.get("reasoning", "")
        assert len(reasoning) >= 30, f"Reasoning too short: {reasoning!r}"

    def test_risk_assessor_output(self, response):
        # risk_flags must be a list (may be empty)
        assert isinstance(response.get("risk_flags"), list)

    def test_ticker_matches_request(self, response):
        assert response.get("ticker") == "RELIANCE"

    def test_key_metrics_non_empty(self, response):
        assert len(response.get("key_metrics", {})) > 0


# ══════════════════════════════════════════════════════════════════════════
# 7. NSE-Fetcher Tools (unit — no server needed)
# ══════════════════════════════════════════════════════════════════════════

class TestNSEFetcherTools:
    """yfinance wrapper returns correct data shapes."""

    def test_get_ohlcv_returns_candles(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_ohlcv
        candles = get_ohlcv("RELIANCE", interval="1d", days=10)
        assert len(candles) > 0
        c = candles[-1]
        assert c.ticker == "RELIANCE"
        assert c.close > 0
        assert c.high >= c.close >= c.low >= 0
        assert c.volume >= 0

    def test_get_ohlcv_nifty_index(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_ohlcv
        candles = get_ohlcv("NIFTY", interval="1d", days=5)
        assert len(candles) > 0
        assert all(c.close > 10000 for c in candles), "NIFTY should be >10000"

    def test_get_info_fields(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_info
        info = get_info("INFY")
        assert "current_price" in info
        assert "52w_high" in info
        assert "52w_low" in info
        assert info.get("current_price", 0) > 0

    def test_52w_high_gte_low(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_info
        info = get_info("RELIANCE")
        high = info.get("52w_high") or 0
        low = info.get("52w_low") or 0
        if high and low:
            assert high >= low, f"52w_high({high}) < 52w_low({low})"

    def test_option_chain_structure(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_option_chain_data
        result = get_option_chain_data("RELIANCE")
        assert "symbol" in result
        assert "expiries" in result
        # expiries may be empty if options unavailable via yfinance for .NS
        assert isinstance(result["expiries"], list)

    def test_ns_suffix_auto_appended(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import _to_yf_symbol
        assert _to_yf_symbol("RELIANCE") == "RELIANCE.NS"
        assert _to_yf_symbol("NIFTY") == "^NSEI"
        assert _to_yf_symbol("RELIANCE.NS") == "RELIANCE.NS"


# ══════════════════════════════════════════════════════════════════════════
# 8. Qdrant Store (unit — pure Python fallback, no Docker needed)
# ══════════════════════════════════════════════════════════════════════════

class TestQdrantStore:
    """Qdrant store in list-fallback mode works correctly."""

    @pytest.fixture
    def store(self):
        from mcp_servers.fundamental_data.qdrant_store import QdrantStore
        s = QdrantStore()
        # Force list fallback regardless of QDRANT_URL
        s._client = None
        return s

    def test_upsert_and_search(self, store):
        store.upsert_chunk(
            "chunk-1",
            "Revenue grew 18% YoY to ₹2.3L crore in FY25. EBITDA margin improved.",
            {"ticker": "RELIANCE", "fiscal_year": 2025, "report_type": "annual_report", "source_file": "AR_FY25.pdf"},
        )
        results = store.search("RELIANCE", "revenue growth EBITDA")
        assert len(results) >= 1
        assert results[0]["ticker"] == "RELIANCE"

    def test_filter_by_ticker(self, store):
        store.upsert_chunk("r1", "Infosys revenue Q3 FY25", {"ticker": "INFY", "fiscal_year": 2025, "report_type": "quarterly_results", "source_file": "Q3.pdf"})
        store.upsert_chunk("r2", "Reliance revenue Q3 FY25", {"ticker": "RELIANCE", "fiscal_year": 2025, "report_type": "quarterly_results", "source_file": "Q3.pdf"})
        # Search for INFY only
        results = store.search("INFY", "revenue")
        all_tickers = {r.get("ticker") for r in results}
        assert "RELIANCE" not in all_tickers, "Cross-ticker contamination in search"

    def test_list_reports(self, store):
        store.upsert_chunk("r3", "Annual report text", {"ticker": "WIPRO", "fiscal_year": 2025, "report_type": "annual_report", "source_file": "WIPRO_AR.pdf"})
        reports = store.list_reports("WIPRO")
        assert len(reports) >= 1
        assert any(r.get("source_file") == "WIPRO_AR.pdf" for r in reports)

    def test_no_results_for_unknown_ticker(self, store):
        results = store.search("XYZUNKNOWN123", "anything")
        assert results == []


# ══════════════════════════════════════════════════════════════════════════
# 9. Error Handling Flow
# ══════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """API returns proper errors for bad inputs."""

    def test_empty_query_returns_422(self, client):
        r = client.post("/analyze", json={"query": ""})
        assert r.status_code == 422

    def test_missing_query_field_returns_422(self, client):
        r = client.post("/analyze", json={"ticker": "RELIANCE"})
        assert r.status_code == 422

    def test_whitespace_only_query_returns_422(self, client):
        r = client.post("/analyze", json={"query": "   "})
        assert r.status_code == 422

    def test_invalid_json_returns_422(self, client):
        r = client.post(
            "/analyze",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422

    def test_response_is_json(self, client):
        r = client.get("/health")
        assert r.headers["content-type"].startswith("application/json")


# ══════════════════════════════════════════════════════════════════════════
# 10. Sandbox Safety (unit)
# ══════════════════════════════════════════════════════════════════════════

class TestSandboxSafety:
    """Restricted exec blocks dangerous operations."""

    def _run(self, script, data=None):
        from agents.technical_analyst.sandbox import run_indicator_script
        import numpy as np
        if data is None:
            data = [{"open": x, "high": x+2, "low": x-2, "close": x, "volume": 1000}
                    for x in range(1000, 1060)]
        return run_indicator_script(script, data)

    def test_valid_rsi_script(self):
        result = self._run(
            "result = {'rsi': round(float(ta.rsi(close, 14).dropna().iloc[-1]), 2)}"
        )
        assert "rsi" in result
        assert 0 <= result["rsi"] <= 100

    def test_valid_macd_script(self):
        result = self._run(
            "m = ta.macd(close); result = {'histogram': round(float(m.iloc[-1,0] - m.iloc[-1,2]),4)}"
        )
        assert "histogram" in result

    def test_import_blocked_in_sandbox(self):
        from agents.technical_analyst.sandbox import SandboxError
        with pytest.raises(SandboxError):
            self._run("import subprocess; result = {}")

    def test_os_access_blocked(self):
        from agents.technical_analyst.sandbox import SandboxError
        with pytest.raises((SandboxError, NameError)):
            self._run("result = {'path': os.listdir('/')}")

    def test_timeout_enforced(self):
        from agents.technical_analyst.sandbox import SandboxTimeout, run_indicator_script
        data = [{"open": x, "high": x+1, "low": x-1, "close": x, "volume": 100}
                for x in range(1000, 1060)]
        with pytest.raises(SandboxTimeout):
            run_indicator_script(
                "i = 0\nwhile True: i += 1",
                data, timeout_seconds=0.5,
            )

    def test_result_must_be_dict(self):
        from agents.technical_analyst.sandbox import SandboxError
        with pytest.raises(SandboxError):
            self._run("result = 'not a dict'")
