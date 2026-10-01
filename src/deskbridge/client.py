"""
HTTP client for Freshdesk API v2.

Handles:
  - Basic auth (API key as username, "X" as password)
  - HTTP 429 with Retry-After header (caps wait at 60 s)
  - HTTP 5xx with exponential backoff + jitter
  - Network errors (timeout, connection errors) with backoff
  - Hard fails on 401/403/404 (not retried)
"""
import asyncio
import logging
import random
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("deskbridge")


class FreshdeskError(Exception):
    """Raised for all non-retryable Freshdesk API errors."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.message = message


class FreshdeskClient:
    """Async Freshdesk API client with retry / backoff logic."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.s = settings
        self._http = httpx.AsyncClient(
            base_url=f"https://{settings.domain}.freshdesk.com/api/v2",
            auth=(settings.api_key, "X"),
            timeout=settings.timeout_s,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    # ------------------------------------------------------------------
    # Backoff helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _backoff(attempt: int) -> float:
        """Exponential backoff: 1, 2, 4, 8, 16 s with 0–0.5 s jitter."""
        return min(30.0, 2.0 ** attempt) + random.uniform(0, 0.5)

    @staticmethod
    def _retry_after(resp: httpx.Response, attempt: int) -> float:
        """Parse Retry-After header; fall back to exponential backoff. Cap at 60 s."""
        raw = resp.headers.get("Retry-After")
        try:
            return min(60.0, max(0.0, float(raw)))
        except (TypeError, ValueError):
            return FreshdeskClient._backoff(attempt)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET *path* with retry logic. Returns parsed JSON on success."""
        last = self.s.max_retries

        for attempt in range(last + 1):
            try:
                resp = await self._http.get(path, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == last:
                    raise FreshdeskError(0, f"network error: {exc}") from exc
                wait = self._backoff(attempt)
                log.warning("network error (attempt %d/%d), retrying in %.1fs: %s",
                            attempt + 1, last + 1, wait, exc)
                await asyncio.sleep(wait)
                continue

            # --- rate limited ---
            if resp.status_code == 429:
                if attempt == last:
                    raise FreshdeskError(429, "rate limit: retries exhausted")
                wait = self._retry_after(resp, attempt)
                remaining = resp.headers.get("X-Ratelimit-Remaining", "?")
                log.warning("429 received (remaining=%s), sleeping %.1fs (attempt %d/%d)",
                            remaining, wait, attempt + 1, last + 1)
                await asyncio.sleep(wait)
                continue

            # --- server error ---
            if resp.status_code >= 500:
                if attempt == last:
                    raise FreshdeskError(resp.status_code, "server error: retries exhausted")
                wait = self._backoff(attempt)
                log.warning("HTTP %d (attempt %d/%d), retrying in %.1fs",
                            resp.status_code, attempt + 1, last + 1, wait)
                await asyncio.sleep(wait)
                continue

            # --- client errors (not retried) ---
            if resp.status_code == 401:
                raise FreshdeskError(
                    401,
                    "authentication failed: check FRESHDESK_API_KEY and FRESHDESK_DOMAIN",
                )
            if resp.status_code == 403:
                raise FreshdeskError(
                    403,
                    "forbidden: the API key lacks read permission for this resource",
                )
            if resp.status_code == 404:
                raise FreshdeskError(404, "not found")
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("description", resp.text[:200])
                except Exception:
                    detail = resp.text[:200]
                raise FreshdeskError(resp.status_code, str(detail))

            # --- success ---
            return resp.json()

        raise FreshdeskError(0, "unreachable")  # pragma: no cover

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "FreshdeskClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
