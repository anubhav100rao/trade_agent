"""
Synthesis Agent — full Phase 2 version.
Aggregates technical + fundamental + sentiment + risk flags → Recommendation.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_core.messages import HumanMessage, SystemMessage
from libs.domain_models.recommendation import Recommendation, TradeSignal, RiskFlag
from libs.llm import get_llm


_SYSTEM_PROMPT = """
You are a senior equity analyst synthesizing inputs across technical, fundamental, and sentiment dimensions.

Return ONLY this JSON:
{
  "signal": "BUY" | "SELL" | "HOLD" | "AVOID",
  "confidence": float 0.0-1.0,
  "reasoning": "2-4 sentences citing specific data points from all available analyses",
  "summary": "one sentence for a dashboard card"
}

Weighting by query type:
  - Intraday / short-term → technical 60%, sentiment 30%, fundamental 10%
  - Swing / positional    → technical 40%, fundamental 40%, sentiment 20%
  - Long-term             → fundamental 60%, technical 20%, sentiment 20%

Rules:
  - Confidence > 0.75 only when multiple dimensions agree
  - Never invent data — only reference what is provided
  - If data is insufficient, return HOLD with low confidence
"""


def synthesize(
    ticker: str,
    query: str,
    technical_result: dict | None,
    fundamental_result: dict | None,
    sentiment_result: dict | None,
    risk_flags: list[str],
) -> dict:
    ta = technical_result or {}
    fa = fundamental_result or {}
    sa = sentiment_result or {}

    fund_section = ""
    if fa:
        fund_section = f"""
=== Fundamental Analysis ===
Signal:         {fa.get('signal', 'N/A')}
PE Ratio:       {fa.get('pe_ratio', 'N/A')}
Highlights:     {fa.get('positive_highlights', [])}
Red Flags:      {fa.get('red_flags', [])}
Summary:        {fa.get('summary', 'N/A')}
"""

    context = f"""
Ticker: {ticker}
Query: {query}

=== Technical Analysis ===
Signal:         {ta.get('signal', 'N/A')}
Confidence:     {ta.get('confidence', 'N/A')}
RSI:            {ta.get('rsi', 'N/A')}
MACD:           {ta.get('macd_signal', 'N/A')}
BB Position:    {ta.get('bb_position', 'N/A')}
Price:          {ta.get('current_price', 'N/A')}
52w High/Low:   {ta.get('fifty_two_week_high', 'N/A')} / {ta.get('fifty_two_week_low', 'N/A')}
{fund_section}
=== Sentiment Analysis ===
Score:          {sa.get('score', 'N/A')} (-1 to +1)
Label:          {sa.get('label', 'N/A')}
Headlines:      {sa.get('headline_count', 0)} articles
Top:            {json.dumps(sa.get('top_headlines', [])[:3])}

=== Risk Flags ===
{', '.join(risk_flags) if risk_flags else 'None'}

Synthesize a final recommendation JSON.
"""
    llm = get_llm(temperature=0.1)
    response = llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=context)])
    raw = response.content.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"signal": "HOLD", "confidence": 0.3, "reasoning": raw[:400], "summary": f"Analysis for {ticker}"}

    key_metrics = {}
    for k, v in [("rsi", ta.get("rsi")), ("macd", ta.get("macd_signal")),
                 ("price", ta.get("current_price")), ("pe", fa.get("pe_ratio")),
                 ("sentiment_score", sa.get("score"))]:
        if v is not None:
            key_metrics[k] = v

    sources = []
    if ta:
        sources.append(f"yfinance:{ticker}.NS")
    if fa.get("sources"):
        sources.extend(fa["sources"])
    if sa.get("headline_count", 0) > 0:
        sources.extend(["moneycontrol_rss", "economictimes_rss"])

    agents_used = [a for a, d in [
        ("technical_analyst", ta), ("fundamental_analyst", fa), ("sentiment_watchdog", sa)
    ] if d] + (["risk_assessor"] if risk_flags else []) + ["synthesis"]

    valid_flags = set(f.value for f in RiskFlag)
    return Recommendation(
        ticker=ticker,
        query=query,
        signal=TradeSignal(parsed.get("signal", "HOLD")),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.4)))),
        reasoning=parsed.get("reasoning", ""),
        summary=parsed.get("summary", ""),
        key_metrics=key_metrics,
        risk_flags=[RiskFlag(f) for f in risk_flags if f in valid_flags],
        top_headlines=sa.get("top_headlines", [])[:5],
        sources=sources,
        agents_used=agents_used,
        technical_data=ta or None,
        fundamental_data=fa or None,
        sentiment_data=sa or None,
    ).model_dump()
