"""
Root Orchestrator LangGraph graph — full Phase 2 version.

Nodes:
  parse_query        → Gemini classifier: ticker + analysis_type
  run_technical      → Technical Analyst (RSI/MACD/BB via sandbox)
  run_fundamental    → Fundamental Analyst (yfinance + Qdrant RAG)
  run_sentiment      → Sentiment Watchdog (MoneyControl + ET RSS)
  synthesize         → Risk Assessor + Synthesis → final Recommendation

Session state persisted via Redis (optional — falls back to in-memory).
"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from agents.orchestrator.state import AnalysisState
from agents.orchestrator.router import classify_query
from agents.technical_analyst.workflow import run_technical_analysis
from agents.fundamental_analyst.workflow import run_fundamental_analysis
from agents.sentiment_watchdog.workflow import run_sentiment_analysis
from agents.risk_assessor.workflow import assess_risk
from agents.synthesis.workflow import synthesize


# ── Nodes ────────────────────────────────────────────────────────

def parse_query_node(state: AnalysisState) -> dict:
    routing = classify_query(state["user_query"])
    return {"ticker": routing["ticker"], "analysis_type": routing["analysis_type"], "error": None}


def run_technical_node(state: AnalysisState) -> dict:
    try:
        result = run_technical_analysis(
            ticker=state["ticker"], query=state["user_query"], interval="1d", days=60
        )
        return {"technical_result": result}
    except Exception as e:
        return {"technical_result": None, "error": f"technical_analyst: {e}"}


def run_fundamental_node(state: AnalysisState) -> dict:
    try:
        result = run_fundamental_analysis(ticker=state["ticker"], query=state["user_query"])
        return {"fundamental_result": result}
    except Exception as e:
        return {"fundamental_result": None}


def run_sentiment_node(state: AnalysisState) -> dict:
    try:
        result = run_sentiment_analysis(ticker=state["ticker"], query=state["user_query"], hours_back=6)
        return {"sentiment_result": result}
    except Exception:
        return {"sentiment_result": None}


def synthesize_node(state: AnalysisState) -> dict:
    risk_flags = assess_risk(
        technical_result=state.get("technical_result") or {},
        sentiment_result=state.get("sentiment_result"),
    )
    recommendation = synthesize(
        ticker=state["ticker"],
        query=state["user_query"],
        technical_result=state.get("technical_result"),
        fundamental_result=state.get("fundamental_result"),
        sentiment_result=state.get("sentiment_result"),
        risk_flags=risk_flags,
    )
    return {"final_recommendation": recommendation}


# ── Graph builder ─────────────────────────────────────────────────

def build_orchestrator_graph(use_redis: bool = False):
    g = StateGraph(AnalysisState)
    g.add_node("parse_query", parse_query_node)
    g.add_node("run_technical", run_technical_node)
    g.add_node("run_fundamental", run_fundamental_node)
    g.add_node("run_sentiment", run_sentiment_node)
    g.add_node("synthesize", synthesize_node)

    g.set_entry_point("parse_query")
    g.add_edge("parse_query", "run_technical")
    g.add_edge("run_technical", "run_fundamental")
    g.add_edge("run_fundamental", "run_sentiment")
    g.add_edge("run_sentiment", "synthesize")
    g.add_edge("synthesize", END)

    # Optional Redis checkpointing for multi-turn sessions
    checkpointer = None
    if use_redis:
        try:
            from langgraph.checkpoint.redis import RedisSaver
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            checkpointer = RedisSaver.from_conn_string(redis_url)
        except Exception:
            pass  # Redis not available — run stateless

    return g.compile(checkpointer=checkpointer)


_USE_REDIS = os.getenv("REDIS_URL", "") != ""
orchestrator_graph = build_orchestrator_graph(use_redis=_USE_REDIS)


def analyze(query: str, session_id: str | None = None) -> dict:
    """
    Main entry point. Returns a Recommendation dict.

    Args:
        query:      Natural language question about a stock/market.
        session_id: Optional — enables multi-turn follow-up via Redis.
    """
    sid = session_id or str(uuid.uuid4())
    initial: AnalysisState = {
        "user_query": query,
        "session_id": sid,
        "ticker": "",
        "analysis_type": "composite",
        "technical_result": None,
        "fundamental_result": None,
        "sentiment_result": None,
        "final_recommendation": None,
        "error": None,
    }
    config = {"configurable": {"thread_id": sid}} if _USE_REDIS else {}
    result = orchestrator_graph.invoke(initial, config=config)
    return result.get("final_recommendation") or {"error": result.get("error"), "query": query}
