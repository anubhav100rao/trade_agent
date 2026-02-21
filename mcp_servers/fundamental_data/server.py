"""
fundamental-data MCP Server.

Uses Qdrant (in-memory or local) to search indexed financial documents.
Falls back gracefully to yfinance fundamentals when Qdrant has no data.

Tools:
  search_reports(ticker, query, fiscal_year)       → List of report chunks
  get_financial_summary(ticker)                     → Key financial metrics
  list_available_reports(ticker)                    → Indexed report metadata
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import fastmcp
from mcp_servers.fundamental_data.qdrant_store import QdrantStore
from mcp_servers.nse_fetcher.yfinance_fallback import get_info

mcp = fastmcp.FastMCP(
    name="fundamental-data",
    instructions=(
        "Searches indexed financial reports (annual reports, earnings calls, DRHP) "
        "using hybrid vector search. Falls back to yfinance for basic financial metrics "
        "when no reports are indexed. Use search_reports for specific questions from documents."
    ),
)

_store = QdrantStore()


@mcp.tool()
def search_reports(ticker: str, query: str, fiscal_year: int | None = None) -> dict:
    """
    Search indexed financial reports for a ticker using semantic + keyword search.

    Args:
        ticker:      NSE symbol e.g. RELIANCE, INFY.
        query:       Natural language question e.g. 'revenue growth Q3 FY25'.
        fiscal_year: Optional filter by year e.g. 2025.

    Returns:
        Dict with ticker, query, results (list of text chunks + metadata).
    """
    results = _store.search(ticker=ticker, query=query, fiscal_year=fiscal_year, limit=5)
    return {
        "ticker": ticker.upper(),
        "query": query,
        "results": results,
        "count": len(results),
        "source": "qdrant" if results else "no_data",
    }


@mcp.tool()
def get_financial_summary(ticker: str) -> dict:
    """
    Get key financial metrics for a stock (PE, PB, EPS, dividend yield, etc.)
    Sources from yfinance — always available without indexing.

    Args:
        ticker: NSE symbol e.g. RELIANCE.

    Returns:
        Dict with financial metrics and metadata.
    """
    info = get_info(ticker)
    return {
        "ticker": ticker.upper(),
        "metrics": info,
        "source": "yfinance",
    }


@mcp.tool()
def list_available_reports(ticker: str) -> dict:
    """
    List all financial reports indexed in Qdrant for a ticker.

    Args:
        ticker: NSE symbol e.g. RELIANCE.

    Returns:
        Dict with ticker and list of available report metadata.
    """
    reports = _store.list_reports(ticker)
    return {
        "ticker": ticker.upper(),
        "reports": reports,
        "count": len(reports),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
