"""
FastAPI gateway for the Indian Market Financial Analysis Agent.

Endpoints:
  GET  /health     — liveness check
  POST /analyze    — main analysis endpoint
  GET  /docs       — Swagger UI (auto-generated)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.schemas import QueryRequest, HealthResponse
from agents.orchestrator.workflow import analyze

# ── App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="Indian Market Financial Analysis Agent",
    description=(
        "Multi-agent decision support system for Indian stock markets (NSE/BSE). "
        "Analyzes stocks and F&O instruments using technical analysis, news sentiment, "
        "and provides cited recommendations. No trade execution."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ───────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Liveness check — returns service status."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        services={
            "gemini": "configured" if os.getenv("GEMINI_API_KEY") else "missing_key",
            "dhan": "configured" if os.getenv("DHAN_CLIENT_ID") else "fallback_yfinance",
        },
    )


@app.post("/analyze", tags=["Analysis"])
async def analyze_query(request: QueryRequest):
    """
    Analyze a stock or market query and return a structured recommendation.

    The system will:
    1. Extract the ticker and classify query intent
    2. Run Technical Analyst (RSI, MACD, Bollinger Bands)
    3. Run Sentiment Watchdog (recent news from MoneyControl, ET)
    4. Assess contextual risk flags
    5. Synthesize a final recommendation with citations

    Example queries:
    - "Is RELIANCE a good buy today?"
    - "Show me NIFTY technical analysis"
    - "What does the market sentiment say about INFY?"
    - "Analyze TATAMOTORS for a swing trade"
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Query cannot be empty")

    # If ticker provided in request, prepend to query for better routing
    if request.ticker:
        query = f"{request.ticker.upper()}: {query}"

    try:
        result = analyze(query=query, session_id=request.session_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}. Please retry.",
        )


# ── Dev runner ───────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )
