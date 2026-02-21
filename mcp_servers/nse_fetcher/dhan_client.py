"""
Rate-limited async client for the Dhan API.
Falls back gracefully to yfinance if credentials are not set.
"""
import os
import asyncio
import time
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


DHAN_BASE_URL = "https://api.dhan.co"


class TokenBucket:
    """Simple async token bucket rate limiter."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate        # tokens per second
        self.capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last_refill = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self.rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


class DhanClient:
    """
    Async wrapper around the Dhan API.
    Rate limited to 10 data requests/second (Dhan limit).
    """

    def __init__(self):
        self.client_id = os.getenv("DHAN_CLIENT_ID", "")
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
        self.available = bool(self.client_id and self.access_token)
        self._rate_limiter = TokenBucket(rate=8.0, capacity=10.0)  # 8/s conservative
        self._http: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> dict:
        return {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(base_url=DHAN_BASE_URL, timeout=15.0)
        return self._http

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_historical_data(
        self,
        security_id: str,
        exchange_segment: str,
        instrument_type: str,
        from_date: str,
        to_date: str,
    ) -> list[dict]:
        """Fetch historical OHLCV data from Dhan."""
        await self._rate_limiter.acquire()
        client = await self._get_client()
        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "fromDate": from_date,
            "toDate": to_date,
        }
        resp = await client.post(
            "/charts/historical", headers=self.headers, json=payload
        )
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_option_chain(self, under_security_id: str, expiry_date: str) -> dict:
        """Fetch option chain for a symbol+expiry."""
        await self._rate_limiter.acquire()
        client = await self._get_client()
        params = {
            "UnderlyingScrip": under_security_id,
            "UnderlyingSeg": "IDX_I",
            "Expiry": expiry_date,
        }
        resp = await client.get(
            "/optionchain", headers=self.headers, params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()
