import logging
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class AsyncJSONCollector:
    """Small async client wrapper for high-frequency JSON APIs."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = httpx.Timeout(settings.request_timeout_seconds)

    async def fetch_json(self, url: str | None, *, headers: Mapping[str, str] | None = None) -> Any:
        if not url or "example.com" in url:
            logger.warning("Skipping external JSON fetch because URL is not configured: %s", url)
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.warning("External JSON fetch failed for %s: %s", url, exc)
            return None

    async def fetch_text(self, url: str | None) -> str | None:
        if not url or "example.com" in url:
            logger.warning("Skipping external text fetch because URL is not configured: %s", url)
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            logger.warning("External text fetch failed for %s: %s", url, exc)
            return None

    async def fetch_primary_market_data(self) -> Any:
        logger.warning("Legacy primary market fetch is deprecated; use TelemetryProviderConnector.")
        return None
