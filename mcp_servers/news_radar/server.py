"""
News Radar MCP Server.

Tools:
  get_recent_news(ticker, hours_back) → list of NewsItem dicts
  get_sector_news(sector, hours_back) → list of NewsItem dicts
  get_macro_events()                  → list of upcoming events
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import fastmcp
from mcp_servers.news_radar.rss_scraper import fetch_moneycontrol_news, fetch_et_news

mcp = fastmcp.FastMCP(
    name="news-radar",
    instructions=(
        "Fetches recent financial news for Indian markets from MoneyControl and Economic Times. "
        "Use get_recent_news to fetch ticker-specific news. "
        "Use get_sector_news for broader sector trends."
    ),
)


@mcp.tool()
def get_recent_news(ticker: str, hours_back: int = 6) -> dict:
    """
    Fetch recent news articles for a specific NSE ticker.

    Args:
        ticker:     Stock symbol e.g. RELIANCE, INFY, TATAMOTORS.
        hours_back: How many hours back to search (default 6).

    Returns:
        Dict with 'ticker', 'articles' list, 'count', 'hours_back'.
    """
    mc_articles = fetch_moneycontrol_news(ticker, hours_back=hours_back)
    et_articles = fetch_et_news(ticker, hours_back=hours_back)
    all_articles = mc_articles + et_articles
    # Sort by recency (latest first)
    all_articles.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return {
        "ticker": ticker.upper(),
        "articles": all_articles[:15],
        "count": len(all_articles),
        "hours_back": hours_back,
    }


@mcp.tool()
def get_sector_news(sector: str, hours_back: int = 6) -> dict:
    """
    Fetch general market and sector news.

    Args:
        sector:     e.g. "banking", "auto", "IT", "pharma", or "market" for broad news.
        hours_back: How many hours back to search (default 6).

    Returns:
        Dict with 'sector', 'articles' list, 'count'.
    """
    mc_articles = fetch_moneycontrol_news(sector, hours_back=hours_back)
    et_articles = fetch_et_news(sector, hours_back=hours_back)
    all_articles = (mc_articles + et_articles)[:20]
    return {
        "sector": sector,
        "articles": all_articles,
        "count": len(all_articles),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
