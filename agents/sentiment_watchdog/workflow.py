"""
Sentiment Watchdog Agent.

Fetches recent news via news-radar MCP tools,
scores overall sentiment, returns SentimentAnalysis.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from mcp_servers.news_radar.rss_scraper import fetch_moneycontrol_news, fetch_et_news
from libs.domain_models.analysis import SentimentAnalysis, NewsItem
from libs.llm import get_llm



_SYSTEM_PROMPT = """
You are a sentiment analyst for Indian financial markets.
Analyze the provided news headlines and return a JSON object:
{
  "score": float between -1.0 (very negative) and 1.0 (very positive),
  "label": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
  "summary": "one sentence describing overall market sentiment",
  "confidence": float 0.0-1.0
}
Base the score purely on factual sentiment from the headlines. 
Score 0 if news is mixed or irrelevant to the ticker.
"""


def run_sentiment_analysis(ticker: str, query: str, hours_back: int = 6) -> dict:
    """Fetch news, score sentiment using Gemini, return SentimentAnalysis dict."""
    mc = fetch_moneycontrol_news(ticker, hours_back=hours_back)
    et = fetch_et_news(ticker, hours_back=hours_back)
    all_articles = (mc + et)[:20]

    news_items = [
        NewsItem(
            title=a["title"],
            source=a["source"],
            url=a.get("url"),
            published_at=a.get("published_at"),
        )
        for a in all_articles
    ]
    headlines = [a["title"] for a in all_articles]

    if not headlines:
        return SentimentAnalysis(
            ticker=ticker,
            score=0.0,
            label="NEUTRAL",
            headline_count=0,
            top_headlines=[],
            news_items=[],
            hours_back=hours_back,
            summary=f"No recent news found for {ticker} in the last {hours_back} hours.",
            confidence=0.1,
        ).model_dump()

    llm = get_llm(temperature=0.1)


    user_prompt = f"""
Ticker: {ticker}
User Query: {query}
Recent headlines (last {hours_back} hours):
{chr(10).join(f'- {h}' for h in headlines[:15])}

Return the JSON sentiment object.
"""
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
        parsed = {"score": 0.0, "label": "NEUTRAL", "summary": "Parse error", "confidence": 0.1}

    score = max(-1.0, min(1.0, float(parsed.get("score", 0.0))))

    return SentimentAnalysis(
        ticker=ticker,
        score=score,
        label=parsed.get("label", "NEUTRAL"),
        headline_count=len(headlines),
        top_headlines=headlines[:5],
        news_items=news_items[:5],
        hours_back=hours_back,
        summary=parsed.get("summary", ""),
        confidence=float(parsed.get("confidence", 0.5)),
    ).model_dump()
