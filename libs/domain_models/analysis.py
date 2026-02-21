from pydantic import BaseModel, Field
from typing import Optional


class TechnicalAnalysis(BaseModel):
    """Output from the Technical Analyst agent."""
    ticker: str
    signal: str  # "BULLISH" | "BEARISH" | "NEUTRAL"

    # Key indicator values
    rsi: Optional[float] = None
    macd_signal: Optional[str] = None   # "bullish_crossover" | "bearish_crossover" | "neutral"
    bb_position: Optional[str] = None  # "above_upper" | "below_lower" | "within"
    put_call_ratio: Optional[float] = None

    # Price levels
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    current_price: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None

    # Human-readable summary (≤500 tokens for Orchestrator)
    summary: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    data_source: str = "yfinance"


class FundamentalAnalysis(BaseModel):
    """Output from the Fundamental Analyst agent."""
    ticker: str
    signal: str  # "POSITIVE" | "NEGATIVE" | "NEUTRAL"

    pe_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None   # percent
    net_profit_margin: Optional[float] = None
    roe: Optional[float] = None  # Return on Equity

    management_sentiment: Optional[str] = None  # "positive" | "cautious" | "negative"
    red_flags: list[str] = Field(default_factory=list)
    positive_highlights: list[str] = Field(default_factory=list)

    # RAG citations
    sources: list[str] = Field(default_factory=list)  # e.g. ["RELIANCE_AR_FY24.pdf#p12"]

    summary: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class NewsItem(BaseModel):
    """A single news article."""
    title: str
    source: str   # "moneycontrol" | "economictimes" | "twitter"
    url: Optional[str] = None
    published_at: Optional[str] = None
    sentiment_score: Optional[float] = None  # -1 to 1


class SentimentAnalysis(BaseModel):
    """Output from the Sentiment Watchdog agent."""
    ticker: str
    score: float = Field(ge=-1.0, le=1.0)   # -1 (very negative) to +1 (very positive)
    label: str  # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    headline_count: int = 0
    top_headlines: list[str] = Field(default_factory=list)
    news_items: list[NewsItem] = Field(default_factory=list)
    hours_back: int = 6  # time window used
    summary: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
