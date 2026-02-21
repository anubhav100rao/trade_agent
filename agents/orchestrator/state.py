from typing import TypedDict, Optional, Literal


class AnalysisState(TypedDict):
    """Shared state across the entire agent graph."""
    user_query: str
    session_id: str
    ticker: str
    analysis_type: Literal["technical", "fundamental", "sentiment", "composite"]
    technical_result: Optional[dict]
    fundamental_result: Optional[dict]
    sentiment_result: Optional[dict]
    final_recommendation: Optional[dict]
    error: Optional[str]
