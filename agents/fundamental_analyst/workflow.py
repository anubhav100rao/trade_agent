"""
Fundamental Analyst Agent.

Retrieves financial report chunks from Qdrant (fundamental-data MCP)
+ yfinance financial metrics, then uses Gemini to synthesize insights.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_core.messages import HumanMessage, SystemMessage
from mcp_servers.fundamental_data.qdrant_store import QdrantStore
from mcp_servers.nse_fetcher.yfinance_fallback import get_info
from libs.domain_models.analysis import FundamentalAnalysis
from libs.llm import get_llm


_SYSTEM_PROMPT = """
You are a fundamental analyst specialising in Indian equities.
Given financial metrics and relevant excerpts from annual reports / earnings calls,
produce a concise analysis in JSON:
{
  "signal": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
  "confidence": float 0.0-1.0,
  "summary": "one sentence for dashboard",
  "reasoning": "2-4 sentences citing specific numbers",
  "positive_highlights": ["list of positives"],
  "red_flags": ["list of concerns"],
  "management_sentiment": "positive" | "cautious" | "negative"
}
Rules:
- Only cite figures that appear in the provided data.
- Red flags: rising debt, falling margins, negative FCF, accounting anomalies.
- Confidence > 0.7 only when multiple data points agree.
"""


def run_fundamental_analysis(ticker: str, query: str) -> dict:
    """
    Pull financial data + report chunks and synthesize via Gemini.
    Returns FundamentalAnalysis dict.
    """
    # 1. yfinance fundamental snapshot (always available)
    info = get_info(ticker)

    # 2. Qdrant RAG (available if PDFs have been indexed)
    store = QdrantStore()
    rag_results = store.search(ticker=ticker, query=query, limit=5)
    sources = [r.get("source_file", "yfinance") for r in rag_results]
    context_chunks = "\n\n---\n".join(r["text"] for r in rag_results) if rag_results else ""

    user_prompt = f"""
Ticker: {ticker.upper()}
User Query: {query}

=== Financial Metrics (yfinance) ===
Current Price:   {info.get('current_price', 'N/A')}
PE Ratio:        {info.get('pe_ratio', 'N/A')}
PB Ratio:        {info.get('pb_ratio', 'N/A')}
EPS (TTM):       {info.get('eps', 'N/A')}
Dividend Yield:  {info.get('dividend_yield', 'N/A')}
Market Cap:      {info.get('market_cap', 'N/A')}
Sector:          {info.get('sector', 'N/A')}

=== Report Excerpts (Qdrant RAG — {len(rag_results)} chunks retrieved) ===
{context_chunks if context_chunks else "No indexed reports. Analysis based on yfinance metrics only."}

Produce the JSON fundamental analysis.
"""
    llm = get_llm(temperature=0.1)
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    raw = response.content.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"signal": "NEUTRAL", "confidence": 0.3, "summary": raw[:150], "reasoning": raw[:300]}

    return FundamentalAnalysis(
        ticker=ticker.upper(),
        signal=parsed.get("signal", "NEUTRAL"),
        confidence=float(parsed.get("confidence", 0.4)),
        summary=parsed.get("summary", ""),
        pe_ratio=info.get("pe_ratio"),
        debt_to_equity=None,   # not in yfinance basic info
        revenue_growth_yoy=None,
        net_profit_margin=None,
        roe=None,
        management_sentiment=parsed.get("management_sentiment"),
        red_flags=parsed.get("red_flags", []),
        positive_highlights=parsed.get("positive_highlights", []),
        sources=sources if sources else ["yfinance"],
    ).model_dump()
