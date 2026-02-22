"""
Technical Analyst LangGraph sub-graph.

Nodes:
  fetch_data        → calls nse-fetcher tools (yfinance fallback)
  compute_indicators → runs indicator script in sandbox
  llm_interpret     → Gemini interprets indicator values
  build_result      → assembles TechnicalAnalysis domain model
"""
import json
import os
import sys
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from agents.technical_analyst.state import TechnicalAnalystState
from agents.technical_analyst.sandbox import run_indicator_script, SandboxError, SandboxTimeout
from mcp_servers.nse_fetcher import yfinance_fallback as yf_client
from libs.domain_models.analysis import TechnicalAnalysis
from libs.llm import get_llm


# ── LLM ─────────────────────────────────────────────────────────
def _get_llm():
    return get_llm(temperature=0.1)



# ── Pre-built indicator script (LLM-writeable in future) ─────────
INDICATOR_SCRIPT = """
results = {}

# RSI (14-period)
rsi_series = ta.rsi(close, length=14)
rsi_val = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else None
results["rsi"] = round(rsi_val, 2) if rsi_val else None

# MACD
macd_df = ta.macd(close, fast=12, slow=26, signal=9)
if macd_df is not None and not macd_df.empty:
    macd_line = macd_df.iloc[-1, 0]   # MACD line
    signal_line = macd_df.iloc[-1, 2] # Signal line
    if macd_line is not None and signal_line is not None:
        results["macd_line"] = round(float(macd_line), 4)
        results["macd_signal_line"] = round(float(signal_line), 4)
        results["macd_signal"] = "bullish_crossover" if macd_line > signal_line else "bearish_crossover"
    else:
        results["macd_signal"] = "neutral"
else:
    results["macd_signal"] = "neutral"

# Bollinger Bands
bb = ta.bbands(close, length=20, std=2)
if bb is not None and not bb.empty:
    upper = float(bb.iloc[-1, 0])
    mid   = float(bb.iloc[-1, 1])
    lower = float(bb.iloc[-1, 2])
    price = float(close.iloc[-1])
    results["bb_upper"] = round(upper, 2)
    results["bb_mid"]   = round(mid, 2)
    results["bb_lower"] = round(lower, 2)
    if price >= upper:
        results["bb_position"] = "above_upper"
    elif price <= lower:
        results["bb_position"] = "below_lower"
    else:
        results["bb_position"] = "within"
else:
    results["bb_position"] = "unknown"

# 20-day SMA
sma20 = ta.sma(close, length=20)
if sma20 is not None and not sma20.dropna().empty:
    results["sma_20"] = round(float(sma20.dropna().iloc[-1]), 2)

# Recent price levels (last 5 sessions)
recent_highs = [round(float(h), 2) for h in list(high.tail(5))]
recent_lows  = [round(float(l), 2) for l in list(low.tail(5))]
results["recent_highs"] = recent_highs
results["recent_lows"]  = recent_lows
results["current_close"] = round(float(close.iloc[-1]), 2)

result = results
"""


def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system.md")
    with open(prompt_path) as f:
        return f.read()


# ── Graph Nodes ──────────────────────────────────────────────────

def fetch_data(state: TechnicalAnalystState) -> dict:
    """Fetch OHLCV and stock info from yfinance."""
    try:
        candles = yf_client.get_ohlcv(
            state["ticker"],
            interval=state.get("interval", "1d"),
            days=state.get("days", 60),
        )
        info = yf_client.get_info(state["ticker"])
        candle_dicts = [
            {
                "open": c.open, "high": c.high,
                "low": c.low, "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        return {"candles": candle_dicts, "stock_info": info, "error": None}
    except Exception as e:
        return {"candles": [], "stock_info": {}, "error": f"fetch_data failed: {e}"}


def compute_indicators(state: TechnicalAnalystState) -> dict:
    """Run the indicator script in the sandbox."""
    if state.get("error") or not state.get("candles"):
        return {"indicators": {}}
    try:
        indicators = run_indicator_script(INDICATOR_SCRIPT, state["candles"])
        return {"indicators": indicators, "error": None}
    except (SandboxError, SandboxTimeout) as e:
        return {"indicators": {}, "error": f"sandbox error: {e}"}


def llm_interpret(state: TechnicalAnalystState) -> dict:
    """Ask Gemini to interpret the calculated indicators."""
    if state.get("error") and not state.get("indicators"):
        return {"llm_analysis": None}

    indicators = state.get("indicators", {})
    info = state.get("stock_info", {})
    ticker = state["ticker"]

    context = f"""
Ticker: {ticker}
Current Price: {info.get('current_price', indicators.get('current_close', 'N/A'))}
52-Week High: {info.get('52w_high', 'N/A')}
52-Week Low: {info.get('52w_low', 'N/A')}
User Query: {state.get('original_query', '')}

Calculated Indicators:
{json.dumps(indicators, indent=2)}

Analyze the above and return your JSON response.
"""
    system_prompt = _load_system_prompt()
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context),
    ])

    # Extract JSON from response
    raw = response.content.strip()
    # Handle markdown code fences
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "signal": "NEUTRAL",
            "confidence": 0.3,
            "summary": f"Analysis for {ticker} (parse error)",
            "reasoning": raw[:300],
            "support_levels": [],
            "resistance_levels": [],
            "risk_flags": [],
        }

    return {"llm_analysis": parsed, "error": None}


def build_result(state: TechnicalAnalystState) -> dict:
    """Assemble the final TechnicalAnalysis model from graph state."""
    analysis = state.get("llm_analysis") or {}
    indicators = state.get("indicators") or {}
    info = state.get("stock_info") or {}

    return {
        "technical_result": TechnicalAnalysis(
            ticker=state["ticker"],
            signal=analysis.get("signal", "NEUTRAL"),
            confidence=float(analysis.get("confidence", 0.4)),
            summary=analysis.get("summary", f"Technical analysis for {state['ticker']}"),
            rsi=indicators.get("rsi"),
            macd_signal=indicators.get("macd_signal"),
            bb_position=indicators.get("bb_position"),
            support_levels=analysis.get("support_levels", indicators.get("recent_lows", [])),
            resistance_levels=analysis.get("resistance_levels", indicators.get("recent_highs", [])),
            current_price=info.get("current_price") or indicators.get("current_close"),
            fifty_two_week_high=info.get("52w_high"),
            fifty_two_week_low=info.get("52w_low"),
            data_source="yfinance",
        ).model_dump()
    }


# ── Build Graph ──────────────────────────────────────────────────

def _should_skip(state: TechnicalAnalystState) -> str:
    return "skip" if state.get("error") and not state.get("candles") else "continue"


def build_technical_analyst_graph():
    g = StateGraph(TechnicalAnalystState)
    g.add_node("fetch_data", fetch_data)
    g.add_node("compute_indicators", compute_indicators)
    g.add_node("llm_interpret", llm_interpret)
    g.add_node("build_result", build_result)

    g.set_entry_point("fetch_data")
    g.add_edge("fetch_data", "compute_indicators")
    g.add_edge("compute_indicators", "llm_interpret")
    g.add_edge("llm_interpret", "build_result")
    g.add_edge("build_result", END)
    return g.compile()


technical_analyst_graph = build_technical_analyst_graph()


def run_technical_analysis(ticker: str, query: str, interval: str = "1d", days: int = 60) -> dict:
    """Main entry point for the Technical Analyst agent."""
    result = technical_analyst_graph.invoke({
        "ticker": ticker,
        "interval": interval,
        "days": days,
        "original_query": query,
        "candles": [],
        "stock_info": {},
        "indicators": {},
        "llm_analysis": None,
        "error": None,
        "technical_result": None,
    })
    return result.get("technical_result", {})
