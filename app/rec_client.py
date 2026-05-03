"""HTTP client for the Rec API."""

from __future__ import annotations

from typing import Any
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import get_settings

settings = get_settings()
logger = logging.getLogger("pickleball_scraper")

REC_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


class RecClient:
    """Thin wrapper around httpx for Rec API calls."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.rec_base_url,
            timeout=settings.http_timeout_seconds,
            headers=REC_HEADERS,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
        before_sleep=lambda retry_state: logger.warning(
            "Retrying Rec API fetch due to error (attempt %s/3)",
            retry_state.attempt_number
        )
    )
    async def fetch_locations(self) -> list[dict[str, Any]]:
        """Fetch availability for the configured organization."""
        params = {
            "organizationSlug": settings.organization_slug,
            "publishedSites": "true",
        }
        response = await self._client.get("/v1/locations/availability", params=params)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
