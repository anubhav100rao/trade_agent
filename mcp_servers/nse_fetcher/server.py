"""
nse-fetcher MCP server — yfinance only.

Tools:
  get_ohlc(symbol, interval, days)     → OHLCV candles
  get_stock_info(symbol)               → price, PE, 52w levels
  get_option_chain(symbol)             → option chain via yfinance
  get_market_overview()                → NIFTY / BANKNIFTY levels
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import fastmcp
from mcp_servers.nse_fetcher.yfinance_fallback import get_ohlcv, get_info, get_option_chain_data

mcp = fastmcp.FastMCP(
    name="nse-fetcher",
    instructions=(
        "Provides live and historical market data for Indian stock markets (NSE/BSE) "
        "via Yahoo Finance. Symbol examples: RELIANCE, INFY, TATAMOTORS, NIFTY, BANKNIFTY. "
        "Use get_ohlc for OHLCV candles, get_stock_info for fundamentals snapshot, "
        "get_option_chain for options data, get_market_overview for index levels."
    ),
)


@mcp.tool()
def get_ohlc(symbol: str, interval: str = "1d", days: int = 60) -> dict:
    """
    Fetch OHLCV candle data for an NSE/BSE symbol.

    Args:
        symbol:   Ticker e.g. RELIANCE, INFY, NIFTY, BANKNIFTY.
        interval: Candle interval — '1m','5m','15m','30m','1h','1d'. Default '1d'.
        days:     Calendar days of history. Default 60.

    Returns:
        Dict with symbol, interval, candles (list of OHLCV dicts), count, source.
    """
    candles = get_ohlcv(symbol, interval=interval, days=days)
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "candles": [c.model_dump(mode="json") for c in candles],
        "count": len(candles),
        "source": "yfinance",
    }


@mcp.tool()
def get_stock_info(symbol: str) -> dict:
    """
    Get snapshot fundamentals and price info for a stock.

    Args:
        symbol: NSE ticker e.g. RELIANCE, HDFCBANK.

    Returns:
        Dict with current_price, 52w_high, 52w_low, pe_ratio, market_cap, sector.
    """
    info = get_info(symbol)
    info["source"] = "yfinance"
    return info


@mcp.tool()
def get_option_chain(symbol: str) -> dict:
    """
    Fetch available option expiries and near-ATM option data for a symbol.

    Args:
        symbol: e.g. RELIANCE, NIFTY.

    Returns:
        Dict with symbol, expiries (list), and nearest expiry calls/puts summary.
    """
    return get_option_chain_data(symbol)


@mcp.tool()
def get_market_overview() -> dict:
    """
    Get current levels for NIFTY 50 and BANKNIFTY indices.

    Returns:
        Dict with nifty_50, banknifty current close prices.
    """
    nifty = get_ohlcv("NIFTY", interval="1d", days=2)
    banknifty = get_ohlcv("BANKNIFTY", interval="1d", days=2)
    return {
        "nifty_50": nifty[-1].close if nifty else None,
        "banknifty": banknifty[-1].close if banknifty else None,
        "source": "yfinance",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
