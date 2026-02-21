"""
News ingestion pipeline.
Polls RSS feeds and upserts recent articles into Qdrant for semantic search.

Usage:
  python -m ingestion.news_pipeline --tickers RELIANCE INFY TATAMOTORS --hours 6
"""
import argparse
import os
import sys
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_servers.fundamental_data.qdrant_store import QdrantStore
from mcp_servers.news_radar.rss_scraper import fetch_moneycontrol_news, fetch_et_news

NEWS_COLLECTION = "news_articles"


def ingest_news(tickers: list[str], hours_back: int = 6, verbose: bool = True) -> int:
    """Fetch and index recent news for a list of tickers into Qdrant."""
    store = QdrantStore()
    total = 0

    for ticker in tickers:
        mc = fetch_moneycontrol_news(ticker, hours_back=hours_back)
        et = fetch_et_news(ticker, hours_back=hours_back)
        articles = mc + et

        if verbose:
            print(f"[news] {ticker}: {len(articles)} articles found")

        for article in articles:
            text = f"{article['title']}. {article.get('summary', '')}"
            store.upsert_chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                metadata={
                    "ticker": ticker.upper(),
                    "report_type": "news",
                    "source_file": article.get("source", "rss"),
                    "url": article.get("url", ""),
                    "published_at": article.get("published_at", ""),
                },
            )
            total += 1

    if verbose:
        print(f"[news] Total articles indexed: {total}")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest recent news into Qdrant")
    parser.add_argument("--tickers", nargs="+", required=True, help="NSE tickers")
    parser.add_argument("--hours", type=int, default=6, help="Hours back to fetch")
    args = parser.parse_args()
    ingest_news(tickers=args.tickers, hours_back=args.hours)
