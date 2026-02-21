from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class OHLCV(BaseModel):
    """Single OHLCV bar."""
    open: float
    high: float
    low: float
    close: float
    volume: int


class Candle(BaseModel):
    """OHLCV candle with metadata."""
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    interval: str = "1d"  # e.g. "15m", "1h", "1d"

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low
