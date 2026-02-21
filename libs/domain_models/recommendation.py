from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class TradeSignal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    AVOID = "AVOID"


class RiskFlag(str, Enum):
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    EARNINGS_UPCOMING = "EARNINGS_UPCOMING"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    STRONG_DOWNTREND = "STRONG_DOWNTREND"
    STRONG_UPTREND = "STRONG_UPTREND"
    OVERBOUGHT = "OVERBOUGHT"
    OVERSOLD = "OVERSOLD"
    NEAR_52W_HIGH = "NEAR_52W_HIGH"
    NEAR_52W_LOW = "NEAR_52W_LOW"


class Recommendation(BaseModel):
    """
    Final output from the Synthesis Agent.
    This is what the API returns to the user.
    """
    ticker: str
    query: str                      # original user query
    signal: TradeSignal
    confidence: float = Field(ge=0.0, le=1.0)

    # Human-readable
    reasoning: str                  # main explanation (2-4 sentences)
    summary: str                    # one-liner for dashboards

    # Supporting data (collapsed for brevity)
    key_metrics: dict = Field(default_factory=dict)  # e.g. {"rsi": 58, "pe": 24.3}
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    top_headlines: list[str] = Field(default_factory=list)

    # Provenance
    sources: list[str] = Field(default_factory=list)
    agents_used: list[str] = Field(default_factory=list)

    # Optional raw sub-agent outputs
    technical_data: Optional[dict] = None
    fundamental_data: Optional[dict] = None
    sentiment_data: Optional[dict] = None

    class Config:
        use_enum_values = True
