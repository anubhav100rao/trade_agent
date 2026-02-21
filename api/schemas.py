from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    """Incoming request to /analyze."""
    query: str = Field(
        ...,
        description="Natural language query e.g. 'Is RELIANCE a good buy today?'",
        examples=["Is RELIANCE a good buy today?", "Show NIFTY option chain analysis"],
    )
    ticker: Optional[str] = Field(
        None,
        description="Optional explicit ticker. If not provided, extracted from query.",
    )
    session_id: Optional[str] = Field(
        None,
        description="Optional session ID for multi-turn conversation continuity.",
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    services: dict = Field(default_factory=dict)
