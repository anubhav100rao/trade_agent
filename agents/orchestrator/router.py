"""
Orchestrator router: classifies user query → routing decision + ticker extraction.
"""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from libs.llm import get_llm



_ROUTER_PROMPT = """
You are a financial query classifier for an Indian market analysis system.
Given a user query, identify:
1. The stock ticker(s) mentioned (NSE symbols, e.g. RELIANCE, INFY, TATAMOTORS, NIFTY, BANKNIFTY)
2. The type of analysis needed

Return ONLY a JSON object:
{
  "ticker": "PRIMARY_TICKER_IN_CAPS",
  "tickers": ["list", "of", "all", "tickers"],
  "analysis_type": "technical" | "fundamental" | "sentiment" | "composite",
  "time_horizon": "intraday" | "swing" | "positional" | "longterm"
}

Classification rules:
- "technical": query about price, chart, RSI, MACD, support, resistance, option chain, F&O
- "fundamental": query about earnings, revenue, PE ratio, debt, balance sheet, management
- "sentiment": query about news, market mood, recent events, announcements
- "composite": any query combining multiple aspects, or general "should I buy?" questions

If no ticker is mentioned, use "NIFTY" as default.
Always return uppercase tickers with NO exchange suffix.
"""


def classify_query(query: str) -> dict:
    """
    Use Gemini to extract ticker and classify analysis type.

    Returns:
        dict with keys: ticker, tickers, analysis_type, time_horizon
    """
    llm = get_llm(temperature=0.0)

    response = llm.invoke([
        SystemMessage(content=_ROUTER_PROMPT),
        HumanMessage(content=f"Query: {query}"),
    ])
    raw = response.content.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract uppercase words as potential tickers
        tokens = re.findall(r'\b[A-Z]{3,12}\b', query.upper())
        ticker = tokens[0] if tokens else "NIFTY"
        parsed = {
            "ticker": ticker,
            "tickers": [ticker],
            "analysis_type": "composite",
            "time_horizon": "swing",
        }

    # Sanitize
    parsed["ticker"] = str(parsed.get("ticker", "NIFTY")).upper().strip()
    parsed["analysis_type"] = parsed.get("analysis_type", "composite")
    return parsed
