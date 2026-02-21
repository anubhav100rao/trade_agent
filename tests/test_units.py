"""
Fast unit tests — no server, no LLM, no network calls beyond yfinance.
Run with:  pytest tests/test_units.py -v
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np


# ─── Domain Models ────────────────────────────────────────────────────────

class TestDomainModels:

    def test_candle_is_bullish(self):
        from datetime import datetime
        from libs.domain_models.candle import Candle
        c = Candle(ticker="RELIANCE", timestamp=datetime.now(),
                   open=1000, high=1050, low=990, close=1040, volume=1_000_000)
        assert c.is_bullish
        assert c.body_size == pytest.approx(40.0)

    def test_candle_is_bearish(self):
        from datetime import datetime
        from libs.domain_models.candle import Candle
        c = Candle(ticker="RELIANCE", timestamp=datetime.now(),
                   open=1040, high=1050, low=990, close=1000, volume=1_000_000)
        assert not c.is_bullish

    def test_recommendation_signal_enum(self):
        from libs.domain_models.recommendation import Recommendation, TradeSignal
        r = Recommendation(
            ticker="INFY", query="test", signal=TradeSignal.BUY,
            confidence=0.75, reasoning="RSI bullish", summary="Buy INFY",
        )
        assert r.signal == "BUY"

    def test_recommendation_confidence_clamp(self):
        """Pydantic should reject confidence > 1."""
        from libs.domain_models.recommendation import Recommendation, TradeSignal
        with pytest.raises(Exception):
            Recommendation(ticker="X", query="q", signal=TradeSignal.HOLD,
                           confidence=1.5, reasoning="x", summary="x")

    def test_risk_flag_values(self):
        from libs.domain_models.recommendation import RiskFlag
        flags = {f.value for f in RiskFlag}
        assert "HIGH_VOLATILITY" in flags
        assert "OVERBOUGHT" in flags
        assert "NEAR_52W_HIGH" in flags


# ─── yfinance Wrapper ─────────────────────────────────────────────────────

class TestYfinanceWrapper:

    def test_symbol_conversion_equity(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import _to_yf_symbol
        assert _to_yf_symbol("RELIANCE") == "RELIANCE.NS"

    def test_symbol_conversion_index(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import _to_yf_symbol
        assert _to_yf_symbol("NIFTY") == "^NSEI"
        assert _to_yf_symbol("BANKNIFTY") == "^NSEBANK"

    def test_symbol_no_double_suffix(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import _to_yf_symbol
        assert _to_yf_symbol("INFY.NS") == "INFY.NS"

    def test_get_ohlcv_returns_list(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_ohlcv
        result = get_ohlcv("WIPRO", interval="1d", days=5)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_ohlcv_ohlc_relationship(self):
        from mcp_servers.nse_fetcher.yfinance_fallback import get_ohlcv
        candles = get_ohlcv("RELIANCE", interval="1d", days=20)
        for c in candles:
            assert c.high >= c.close >= 0
            assert c.high >= c.open >= 0
            assert c.low <= c.close
            assert c.low <= c.open


# ─── Sandbox ──────────────────────────────────────────────────────────────

class TestSandbox:

    def _candles(self, n=50):
        return [{"open": x, "high": x+2, "low": x-2, "close": x+1, "volume": 100_000}
                for x in np.linspace(1000, 1200, n)]

    def test_rsi_result(self):
        from agents.technical_analyst.sandbox import run_indicator_script
        result = run_indicator_script(
            "result = {'rsi': round(float(ta.rsi(close, 14).dropna().iloc[-1]), 2)}",
            self._candles()
        )
        assert 0 <= result["rsi"] <= 100

    def test_bollinger_bands(self):
        from agents.technical_analyst.sandbox import run_indicator_script
        result = run_indicator_script("""
bb = ta.bbands(close, length=20)
# Column names: BBL_* (lower), BBM_* (mid), BBU_* (upper)
upper_col = [c for c in bb.columns if c.startswith('BBU')][0]
lower_col = [c for c in bb.columns if c.startswith('BBL')][0]
result = {
    'bb_upper': round(float(bb[upper_col].iloc[-1]), 2),
    'bb_lower': round(float(bb[lower_col].iloc[-1]), 2),
}
""", self._candles())
        assert result["bb_upper"] > result["bb_lower"]

    def test_import_blocked(self):
        from agents.technical_analyst.sandbox import run_indicator_script, SandboxError
        with pytest.raises(SandboxError):
            run_indicator_script("import subprocess; result = {}",  self._candles())

    def test_timeout_enforced(self):
        from agents.technical_analyst.sandbox import run_indicator_script, SandboxTimeout
        # Use an infinite loop — 'time' is blocked by sandbox so we can't use time.sleep
        with pytest.raises(SandboxTimeout):
            run_indicator_script(
                "i = 0\nwhile True: i += 1",
                self._candles(), timeout_seconds=0.5,
            )

    def test_result_must_be_dict(self):
        from agents.technical_analyst.sandbox import run_indicator_script, SandboxError
        with pytest.raises(SandboxError):
            run_indicator_script("result = [1, 2, 3]", self._candles())


# ─── Qdrant Store ─────────────────────────────────────────────────────────

class TestQdrantStoreFallback:
    """Tests the pure Python list fallback (no Qdrant server needed)."""

    @pytest.fixture
    def store(self):
        from mcp_servers.fundamental_data.qdrant_store import QdrantStore
        s = QdrantStore()
        s._client = None   # force list fallback
        return s

    def test_upsert_and_retrieve(self, store):
        store.upsert_chunk("c1", "Infosys Q3 FY25 revenue grew 12% YoY",
                           {"ticker": "INFY", "fiscal_year": 2025, "report_type": "quarterly_results", "source_file": "q3.pdf"})
        results = store.search("INFY", "revenue growth")
        assert len(results) >= 1

    def test_ticker_isolation(self, store):
        store.upsert_chunk("c2", "Reliance revenue up 20%",
                           {"ticker": "RELIANCE", "fiscal_year": 2025, "report_type": "annual_report", "source_file": "ar.pdf"})
        store.upsert_chunk("c3", "Wipro revenue flat",
                           {"ticker": "WIPRO", "fiscal_year": 2025, "report_type": "annual_report", "source_file": "ar.pdf"})
        rel_results = store.search("RELIANCE", "revenue")
        tickers = {r.get("ticker") for r in rel_results}
        assert "WIPRO" not in tickers


# ─── RSS Scraper ──────────────────────────────────────────────────────────

class TestRSSScraper:

    def test_moneycontrol_fetch_no_crash(self):
        from mcp_servers.news_radar.rss_scraper import fetch_moneycontrol_news
        # May return 0 articles if no match — should never raise
        articles = fetch_moneycontrol_news("RELIANCE", hours_back=48)
        assert isinstance(articles, list)
        for a in articles:
            assert "title" in a
            assert "source" in a

    def test_et_fetch_no_crash(self):
        from mcp_servers.news_radar.rss_scraper import fetch_et_news
        articles = fetch_et_news("INFY", hours_back=48)
        assert isinstance(articles, list)

    def test_articles_have_required_fields(self):
        from mcp_servers.news_radar.rss_scraper import fetch_moneycontrol_news
        articles = fetch_moneycontrol_news("NIFTY", hours_back=72)
        for a in articles[:5]:
            assert isinstance(a.get("title"), str)
            assert a.get("source") in ("moneycontrol", "economictimes")


# ─── Risk Assessor ────────────────────────────────────────────────────────

class TestRiskAssessor:

    def test_overbought_rsi(self):
        from agents.risk_assessor.workflow import assess_risk
        flags = assess_risk({"rsi": 78, "signal": "BULLISH", "confidence": 0.5})
        assert "OVERBOUGHT" in flags

    def test_oversold_rsi(self):
        from agents.risk_assessor.workflow import assess_risk
        flags = assess_risk({"rsi": 25, "signal": "BEARISH", "confidence": 0.5})
        assert "OVERSOLD" in flags

    def test_near_52w_high(self):
        from agents.risk_assessor.workflow import assess_risk
        flags = assess_risk({
            "rsi": 55, "signal": "BULLISH", "confidence": 0.6,
            "current_price": 1400, "fifty_two_week_high": 1410, "fifty_two_week_low": 1000,
        })
        assert "NEAR_52W_HIGH" in flags

    def test_high_volatility_from_bb(self):
        from agents.risk_assessor.workflow import assess_risk
        flags = assess_risk({"rsi": 55, "bb_position": "above_upper"})
        assert "HIGH_VOLATILITY" in flags

    def test_no_flags_when_neutral(self):
        from agents.risk_assessor.workflow import assess_risk
        flags = assess_risk({"rsi": 55, "signal": "NEUTRAL"})
        assert "OVERBOUGHT" not in flags
        assert "OVERSOLD" not in flags

    def test_strong_uptrend(self):
        from agents.risk_assessor.workflow import assess_risk
        flags = assess_risk({"rsi": 60, "signal": "BULLISH", "confidence": 0.82})
        assert "STRONG_UPTREND" in flags
