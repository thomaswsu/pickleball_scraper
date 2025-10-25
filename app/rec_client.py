"""HTTP client for the Rec API."""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings

settings = get_settings()


class RecClient:
    """Thin wrapper around httpx for Rec API calls."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.rec_base_url,
            timeout=settings.http_timeout_seconds,
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
