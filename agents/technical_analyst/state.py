from typing import TypedDict, Optional, Any


class TechnicalAnalystState(TypedDict):
    """State for the Technical Analyst sub-graph."""
    ticker: str
    interval: str                       # e.g. "1d", "15m"
    days: int                           # lookback period
    original_query: str

    # Fetched data
    candles: list[dict]                 # raw OHLCV dicts
    stock_info: dict                    # current price, 52w levels, PE etc.

    # Computed indicators (by sandbox)
    indicators: dict                    # {"rsi": 62.3, "macd_signal": "bullish", ...}

    # LLM interpretation
    llm_analysis: Optional[dict]        # parsed JSON from LLM
    error: Optional[str]                # if any step failed
