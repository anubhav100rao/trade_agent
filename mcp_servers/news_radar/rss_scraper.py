"""
RSS scraper for MoneyControl and Economic Times.
Returns normalised article dicts filtered by keyword and recency.
"""
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional
import re


MC_FEEDS = [
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.moneycontrol.com/rss/results.xml",
]

ET_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/rss.cms",
    "https://economictimes.indiatimes.com/markets/rss.cms",
]


def _parse_pub_date(entry) -> Optional[datetime]:
    """Try to parse published date from an RSS entry."""
    try:
        if hasattr(entry, "published"):
            return parsedate_to_datetime(entry.published).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _is_recent(pub_date: Optional[datetime], hours_back: int) -> bool:
    if pub_date is None:
        return True  # include if we can't determine age
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    return pub_date >= cutoff


def _keyword_match(text: str, keyword: str) -> bool:
    """Case-insensitive keyword match."""
    return keyword.upper() in text.upper()


def _parse_feed(url: str, keyword: str, hours_back: int) -> list[dict]:
    """Parse a single RSS feed and return matching articles."""
    try:
        feed = feedparser.parse(url)
        if feed.bozo:
            return []
        articles = []
        for entry in feed.entries:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")
            pub_date = _parse_pub_date(entry)

            if not _is_recent(pub_date, hours_back):
                continue

            combined = f"{title} {summary}"
            if keyword and not _keyword_match(combined, keyword):
                continue

            articles.append({
                "title": title,
                "summary": summary[:200] if summary else "",
                "url": link,
                "published_at": pub_date.isoformat() if pub_date else None,
                "source": "moneycontrol" if "moneycontrol" in url else "economictimes",
            })
        return articles
    except Exception:
        return []


def fetch_moneycontrol_news(keyword: str, hours_back: int = 6) -> list[dict]:
    articles = []
    for url in MC_FEEDS:
        articles.extend(_parse_feed(url, keyword, hours_back))
    return articles


def fetch_et_news(keyword: str, hours_back: int = 6) -> list[dict]:
    articles = []
    for url in ET_FEEDS:
        articles.extend(_parse_feed(url, keyword, hours_back))
    return articles
