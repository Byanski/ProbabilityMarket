import logging

from app.core.config import Settings
from app.models.schemas import StatsSnapshot
from app.services.collectors import AsyncJSONCollector

logger = logging.getLogger(__name__)


class StatsIngestionEngine:
    """Queries standard stats endpoints and normalizes response buckets."""

    def __init__(self, settings: Settings, collector: AsyncJSONCollector) -> None:
        self.settings = settings
        self.collector = collector

    async def collect(self) -> StatsSnapshot:
        base_url = self.settings.stats_feed_url
        if not base_url or "example.com" in base_url:
            logger.warning("Stats feed URL is not configured; returning placeholder stats.")
            return StatsSnapshot()

        base_url = base_url.rstrip("/")
        standings = await self.collector.fetch_json(f"{base_url}/team_standings")
        scores = await self.collector.fetch_json(f"{base_url}/historical_scores")
        availability = await self.collector.fetch_json(f"{base_url}/player_availability")

        return StatsSnapshot(
            team_standings=self._coerce_list(standings),
            historical_scores=self._coerce_list(scores),
            player_availability=self._coerce_list(availability),
        )

    def _coerce_list(self, payload: object) -> list[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "results", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []
