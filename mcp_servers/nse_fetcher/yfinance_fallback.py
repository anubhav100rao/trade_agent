"""
yfinance wrapper — the single source of market data for the platform.
Handles NSE symbol normalisation, option chains, and info lookups.
"""
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import yfinance as yf
from libs.domain_models.candle import Candle


NSE_INDICES = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "MIDCAP": "^NSEMDCP50",
}

INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "60m", "1d": "1d", "1w": "1wk",
}


def _to_yf_symbol(symbol: str) -> str:
    u = symbol.upper().strip()
    if u in NSE_INDICES:
        return NSE_INDICES[u]
    if u.endswith(".NS") or u.endswith(".BO"):
        return u
    return f"{u}.NS"


def get_ohlcv(symbol: str, interval: str = "1d", days: int = 60) -> list[Candle]:
    """Returns OHLCV candles sorted oldest→newest."""
    yf_sym = _to_yf_symbol(symbol)
    yf_interval = INTERVAL_MAP.get(interval, "1d")
    # yfinance: intraday max 60 days
    period = f"{min(days, 59)}d" if interval != "1d" else f"{days}d"

    hist = yf.Ticker(yf_sym).history(
        period=period, interval=yf_interval, auto_adjust=True
    )
    if hist.empty:
        return []
    return [
        Candle(
            ticker=symbol.upper(),
            timestamp=ts.to_pydatetime(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row.get("Volume", 0)),
            interval=interval,
        )
        for ts, row in hist.iterrows()
    ]


def get_info(symbol: str) -> dict:
    """Key fundamentals + price snapshot."""
    info = yf.Ticker(_to_yf_symbol(symbol)).info or {}
    return {
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "pe_ratio": info.get("trailingPE"),
        "pb_ratio": info.get("priceToBook"),
        "eps": info.get("trailingEps"),
        "market_cap": info.get("marketCap"),
        "dividend_yield": info.get("dividendYield"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "symbol": _to_yf_symbol(symbol),
    }


def get_option_chain_data(symbol: str) -> dict:
    """Fetch option chain — expiries + near-ATM call/put summary."""
    try:
        ticker = yf.Ticker(_to_yf_symbol(symbol))
        expiries = list(ticker.options) if ticker.options else []
        if not expiries:
            return {"symbol": symbol.upper(), "expiries": [], "nearest_expiry": None, "error": "No options data"}

        nearest = expiries[0]
        chain = ticker.option_chain(nearest)
        calls_top = chain.calls.head(5)[["strike", "lastPrice", "openInterest", "impliedVolatility"]].to_dict("records")
        puts_top = chain.puts.head(5)[["strike", "lastPrice", "openInterest", "impliedVolatility"]].to_dict("records")

        # Put-Call Ratio from total OI
        total_call_oi = int(chain.calls["openInterest"].sum())
        total_put_oi = int(chain.puts["openInterest"].sum())
        pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi else None

        return {
            "symbol": symbol.upper(),
            "expiries": expiries[:5],
            "nearest_expiry": nearest,
            "put_call_ratio": pcr,
            "calls_near_atm": calls_top,
            "puts_near_atm": puts_top,
            "source": "yfinance",
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e), "expiries": []}
