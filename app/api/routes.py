import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.analytics.processor import AnalyticsProcessor
from app.core.config import Settings, get_settings
from app.models.schemas import DashboardPayload, EventSnapshot, MarketSnapshot, OutcomeValue, SourceCategory
from app.services.collectors import AsyncJSONCollector
from app.services.parsers import MarketMatrixParser, NewsFeedParser
from app.services.stats_ingestion import StatsIngestionEngine
from app.services.team_stats_connector import TeamStatsConnector
from app.services.telemetry_connector import TelemetryProviderConnector

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "port": 9999,
        "missing_external_config": settings.missing_external_config,
    }

@router.get("/api/categories", response_model=list[SourceCategory])
async def active_categories(settings: Settings = Depends(get_settings)) -> list[SourceCategory]:
    connector = TelemetryProviderConnector(settings)
    return await connector.fetch_active_categories() or _placeholder_categories()

@router.get("/api/index", response_model=DashboardPayload)
async def index_payload(
    category_key: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> DashboardPayload:
    collector = AsyncJSONCollector(settings)
    connector = TelemetryProviderConnector(settings)
    market_parser = MarketMatrixParser()
    news_parser = NewsFeedParser()
    stats_engine = StatsIngestionEngine(settings, collector)
    processor = AnalyticsProcessor(
        baseline_margin=settings.baseline_margin,
        data_format=settings.telemetry_data_format,
    )

    warnings = [
        f"{name} is missing or still points at example.com; using placeholder state."
        for name in settings.missing_external_config
    ]
    for warning in warnings:
        logger.warning(warning)

    categories = await connector.fetch_active_categories() or _placeholder_categories()
    if settings.telemetry_configured and categories == _placeholder_categories():
        warnings.append("Telemetry Source categories are unavailable; using placeholder categories.")
    selected_category = _selected_category(categories, category_key)
    raw_market_payload = await connector.fetch_stream_data(selected_category.key)
    score_history = await connector.fetch_scores(selected_category.key, days_from=3)
    raw_news_payload = await collector.fetch_text(settings.news_feed_url)
    stats_snapshot = await stats_engine.collect()

    events = market_parser.parse(raw_market_payload)
    using_placeholder = False
    if not events:
        if settings.telemetry_configured:
            warnings.append("No live Telemetry Vector rows are available for this Source category.")
        else:
            warnings.append("Telemetry Vector stream is unavailable or empty; using placeholder data points.")
            events = _placeholder_events(selected_category)
            using_placeholder = True
    news_entries = news_parser.parse(raw_news_payload) or _placeholder_news()
    rows = processor.build_index_rows(
        events,
        news_entries,
        {category.key: category for category in categories},
        score_history=score_history,
    )

    return DashboardPayload(
        status="placeholder" if using_placeholder else "live",
        warnings=warnings,
        categories=categories,
        selected_category_key=selected_category.key,
        rows=rows,
        stats=stats_snapshot,
    )

# --- NEW TELEMETRY INTEGRATION ROUTES ---

@router.get("/api/sports/{category_key}/scores")
async def get_scores(
    category_key: str,
    days_from: int | None = Query(default=None, alias="daysFrom"),
    settings: Settings = Depends(get_settings)
) -> Any:
    connector = TelemetryProviderConnector(settings)
    return await connector.fetch_scores(category_key, days_from)

@router.get("/api/sports/{category_key}/events")
async def get_events(
    category_key: str, 
    settings: Settings = Depends(get_settings)
) -> Any:
    connector = TelemetryProviderConnector(settings)
    return await connector.fetch_event_schedule(category_key)

@router.get("/api/sports/{category_key}/events/{event_id}/odds")
async def get_single_event_depth(
    category_key: str, 
    event_id: str, 
    settings: Settings = Depends(get_settings)
) -> Any:
    connector = TelemetryProviderConnector(settings)
    return await connector.fetch_single_event_depth(category_key, event_id)

@router.get("/api/sports/{category_key}/events/{event_id}/markets")
async def get_available_markets(
    category_key: str, 
    event_id: str, 
    settings: Settings = Depends(get_settings)
) -> Any:
    connector = TelemetryProviderConnector(settings)
    return await connector.fetch_available_markets(category_key, event_id)

@router.get("/api/sports/{category_key}/teams/{team_name}/roster")
async def get_team_roster(
    category_key: str,
    team_name: str,
    settings: Settings = Depends(get_settings),
) -> Any:
    connector = TeamStatsConnector(timeout_seconds=settings.request_timeout_seconds)
    return await connector.fetch_team_roster(category_key, team_name)

@router.get("/api/historical/sports/{category_key}/odds")
async def get_historical_snapshot(
    category_key: str,
    date: str = Query(..., description="ISO 8601 timestamp required (e.g., 2026-05-20T12:00:00Z)"),
    settings: Settings = Depends(get_settings)
) -> Any:
    connector = TelemetryProviderConnector(settings)
    return await connector.fetch_historical_snapshot(category_key, date)

# ----------------------------------------

def _selected_category(categories: list[SourceCategory], category_key: str | None) -> SourceCategory:
    if category_key:
        for category in categories:
            if category.key == category_key:
                return category
    preferred_live_keys = (
        "baseball_mlb",
        "basketball_wnba",
        "basketball_nba",
        "icehockey_nhl",
        "americanfootball_nfl",
        "soccer_uefa_champs_league",
    )
    for preferred_key in preferred_live_keys:
        for category in categories:
            if category.key == preferred_key:
                return category
    return categories[0]

def _placeholder_categories() -> list[SourceCategory]:
    return [
        SourceCategory(key="basketball_nba", title="Category Alpha"),
        SourceCategory(key="americanfootball_nfl", title="Category Beta"),
        SourceCategory(key="soccer_epl", title="Category Gamma"),
    ]

def _placeholder_events(selected_category: SourceCategory) -> list[EventSnapshot]:
    return [
        EventSnapshot(
            id=f"sample-{selected_category.key}-001",
            sport_key=selected_category.key,
            commence_time="2026-05-28T19:30:00Z",
            home_team="Metro Analytics",
            away_team="Signal Exchange",
            markets=[
                MarketSnapshot(
                    source_key="source-a",
                    source_title="Source A",
                    market_key="h2h",
                    outcomes=[
                        OutcomeValue(name="Metro Analytics", price=-115),
                        OutcomeValue(name="Signal Exchange", price=104),
                    ],
                ),
                MarketSnapshot(
                    source_key="source-b",
                    source_title="Source B",
                    market_key="h2h",
                    outcomes=[
                        OutcomeValue(name="Metro Analytics", price=-108),
                        OutcomeValue(name="Signal Exchange", price=-102),
                    ],
                ),
                MarketSnapshot(
                    source_key="source-c",
                    source_title="Source C",
                    market_key="spreads",
                    outcomes=[
                        OutcomeValue(name="Metro Analytics", price=-110, point=-2.5),
                        OutcomeValue(name="Signal Exchange", price=-110, point=2.5),
                    ],
                ),
                MarketSnapshot(
                    source_key="source-d",
                    source_title="Source D",
                    market_key="totals",
                    outcomes=[
                        OutcomeValue(name="Over", price=-105, point=47.5),
                        OutcomeValue(name="Under", price=-115, point=47.5),
                    ],
                ),
            ],
        ),
    ]

def _placeholder_news() -> list[dict[str, str]]:
    return [
        {
            "title": "Metro Analytics reports player sidelined before matchup",
            "summary": "A key rotation piece is sidelined, creating a mild negative adjustment.",
            "link": "",
            "published": "",
        },
        {
            "title": "Baseline Vector lists starter out",
            "summary": "Availability feed confirms one starter out and another injured.",
            "link": "",
            "published": "",
        },
    ]
