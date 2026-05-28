import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.models.schemas import SourceCategory

logger = logging.getLogger(__name__)

class TelemetryProviderConnector:
    """Provider-specific connector that exposes neutral Source/Data Point concepts."""

    markets = "h2h,spreads,totals"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = httpx.Timeout(settings.request_timeout_seconds)

    async def fetch_active_categories(self) -> list[SourceCategory]:
        if not self.settings.telemetry_configured:
            logger.warning("Telemetry Source connector is not configured; skipping category scrape.")
            return []

        payload = await self._get_json("/v4/sports", params={"apiKey": self.settings.resolved_telemetry_api_key})
        if not isinstance(payload, list):
            return []

        categories: list[SourceCategory] = []
        for item in payload:
            if isinstance(item, dict):
                if item.get("active") is False or item.get("has_outrights") is True:
                    continue
                key = item.get("key")
                title = item.get("title")
                if isinstance(key, str) and key and isinstance(title, str) and title:
                    categories.append(SourceCategory(key=key, title=title))
        return categories

    async def fetch_stream_data(self, category_key: str) -> Any:
        if not self.settings.telemetry_configured or not category_key:
            return None

        # Fixed URL path
        return await self._get_json(
            f"/v4/sports/{category_key}/odds",
            params={
                "apiKey": self.settings.resolved_telemetry_api_key,
                "regions": self.settings.telemetry_default_region,
                "markets": self.markets,
                "oddsFormat": self.settings.telemetry_data_format,
            },
        )

    async def fetch_scores(self, category_key: str, days_from: int | None = None) -> list[Any]:
        if not self.settings.telemetry_configured or not category_key:
            return []
            
        params: dict[str, str | None] = {"apiKey": self.settings.resolved_telemetry_api_key}
        if days_from is not None:
            params["daysFrom"] = str(days_from)
            
        payload = await self._get_json(f"/v4/sports/{category_key}/scores", params=params)
        return payload if isinstance(payload, list) else []

    async def fetch_event_schedule(self, category_key: str) -> list[Any]:
        if not self.settings.telemetry_configured or not category_key:
            return []
            
        params = {"apiKey": self.settings.resolved_telemetry_api_key}
        payload = await self._get_json(f"/v4/sports/{category_key}/events", params=params)
        return payload if isinstance(payload, list) else []

    async def fetch_single_event_depth(self, category_key: str, event_id: str) -> Any:
        if not self.settings.telemetry_configured or not category_key or not event_id:
            return None
            
        params = {
            "apiKey": self.settings.resolved_telemetry_api_key,
            "regions": self.settings.telemetry_default_region,
            "markets": "h2h,spreads,totals",
            "oddsFormat": self.settings.telemetry_data_format,
        }
        # Fixed URL Path
        return await self._get_json(f"/v4/sports/{category_key}/events/{event_id}/odds", params=params)

    async def fetch_available_markets(self, category_key: str, event_id: str) -> list[Any]:
        if not self.settings.telemetry_configured or not category_key or not event_id:
            return []
            
        params = {"apiKey": self.settings.resolved_telemetry_api_key}
        payload = await self._get_json(f"/v4/sports/{category_key}/events/{event_id}/markets", params=params)
        return payload if isinstance(payload, list) else []

    async def fetch_historical_snapshot(self, category_key: str, snapshot_timestamp: str) -> Any:
        if not self.settings.telemetry_configured or not category_key or not snapshot_timestamp:
            return None
            
        params = {
            "apiKey": self.settings.resolved_telemetry_api_key,
            "date": snapshot_timestamp,
            "regions": self.settings.telemetry_default_region,
            "markets": self.markets,
            "oddsFormat": self.settings.telemetry_data_format,
        }
        return await self._get_json(f"/v4/historical/sports/{category_key}/odds", params=params)

    async def _get_json(self, path: str, params: dict[str, str | None]) -> Any:
        host = self.settings.resolved_telemetry_api_host
        if not host:
            return None

        url = f"{host.rstrip('/')}/{path.lstrip('/')}"
        safe_params = {key: value for key, value in params.items() if value}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=safe_params)
                self._log_quota_headers(response)
                if response.status_code == 429:
                    logger.warning("Telemetry Source rate limit reached for %s.", url)
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Telemetry Source HTTP error for %s: %s", url, exc)
        except httpx.HTTPError as exc:
            logger.warning("Telemetry Source request failed for %s: %s", url, exc)
        except ValueError as exc:
            logger.warning("Telemetry Source returned invalid JSON for %s: %s", url, exc)
        return None

    def _log_quota_headers(self, response: httpx.Response) -> None:
        quota = {
            "x-requests-remaining": response.headers.get("x-requests-remaining"),
            "x-requests-used": response.headers.get("x-requests-used"),
            "x-requests-last": response.headers.get("x-requests-last"),
        }
        if any(value is not None for value in quota.values()):
            logger.warning(
                "Telemetry Source quota metadata: remaining=%s used=%s last=%s",
                quota["x-requests-remaining"],
                quota["x-requests-used"],
                quota["x-requests-last"],
            )
