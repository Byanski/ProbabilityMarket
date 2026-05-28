import logging

from fastapi import APIRouter, Depends, Query

from app.analytics.processor import AnalyticsProcessor
from app.core.config import Settings, get_settings
from app.models.schemas import DashboardPayload, EventSnapshot, MarketSnapshot, OutcomeValue, SourceCategory
from app.services.collectors import AsyncJSONCollector
from app.services.parsers import MarketMatrixParser, NewsFeedParser
from app.services.stats_ingestion import StatsIngestionEngine
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
    raw_news_payload = await collector.fetch_text(settings.news_feed_url)
    stats_snapshot = await stats_engine.collect()

    events = market_parser.parse(raw_market_payload)
    if not events:
        warnings.append("Telemetry Vector stream is unavailable or empty; using placeholder data points.")
        events = _placeholder_events(selected_category)
    news_entries = news_parser.parse(raw_news_payload) or _placeholder_news()
    rows = processor.build_index_rows(
        events,
        news_entries,
        {category.key: category for category in categories},
    )

    return DashboardPayload(
        status="placeholder" if warnings else "live",
        warnings=warnings,
        categories=categories,
        selected_category_key=selected_category.key,
        rows=rows,
        stats=stats_snapshot,
    )


def _selected_category(categories: list[SourceCategory], category_key: str | None) -> SourceCategory:
    if category_key:
        for category in categories:
            if category.key == category_key:
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
