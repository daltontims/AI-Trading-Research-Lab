"""Shared HTTP helper with retries and polite rate limiting."""

from __future__ import annotations

import time

import httpx

USER_AGENT = "ai-trading-research-lab/0.1 (research; simulation only)"
_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=16),
        )
    return _client


def get(url: str, *, params: dict | None = None, retries: int = 4, ok_404: bool = False) -> httpx.Response | None:
    """GET with exponential backoff. Returns None on 404 when ok_404 is set."""
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            r = client().get(url, params=params)
            if r.status_code == 404 and ok_404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    return None
