from typing import Any

import feedparser

from app.models.schemas import EventSnapshot, MarketSnapshot, OutcomeValue


class MarketMatrixParser:
    """Parses the required nested event/bookmakers/markets/outcomes JSON matrix."""

    supported_markets = {"h2h", "spreads", "totals"}

    def parse(self, payload: Any) -> list[EventSnapshot]:
        if not isinstance(payload, list):
            return []

        events: list[EventSnapshot] = []
        for event in payload:
            if not isinstance(event, dict):
                continue

            data_sources = event.get("bookmakers", [])
            parsed_markets: list[MarketSnapshot] = []

            for source in data_sources if isinstance(data_sources, list) else []:
                if not isinstance(source, dict):
                    continue

                source_key = str(source.get("key") or source.get("title") or "unknown-source")
                source_title = str(source.get("title") or source_key)
                markets = source.get("markets", [])
                for market in markets if isinstance(markets, list) else []:
                    if not isinstance(market, dict):
                        continue

                    market_key = str(market.get("key", "unknown-market"))
                    if market_key not in self.supported_markets:
                        continue
                    outcomes = market.get("outcomes", [])
                    parsed_outcomes: list[OutcomeValue] = []

                    for outcome in outcomes if isinstance(outcomes, list) else []:
                        if not isinstance(outcome, dict):
                            continue
                        try:
                            point = outcome.get("point")
                            parsed_outcomes.append(
                                OutcomeValue(
                                    name=str(outcome["name"]),
                                    price=float(outcome["price"]),
                                    point=float(point) if point is not None else None,
                                )
                            )
                        except (KeyError, TypeError, ValueError):
                            continue

                    if parsed_outcomes:
                        parsed_markets.append(
                            MarketSnapshot(
                                source_key=source_key,
                                source_title=source_title,
                                market_key=market_key,
                                outcomes=parsed_outcomes,
                            )
                        )

            if parsed_markets:
                events.append(
                    EventSnapshot(
                        id=str(event.get("id", "unknown-id")),
                        sport_key=str(event.get("sport_key", "unknown-sport")),
                        commence_time=str(event.get("commence_time", "")),
                        home_team=str(event.get("home_team", "Unknown Home")),
                        away_team=str(event.get("away_team", "Unknown Away")),
                        markets=parsed_markets,
                    )
                )

        return events


class NewsFeedParser:
    """Converts RSS/Atom text into searchable news entries."""

    def parse(self, raw_feed: str | None) -> list[dict[str, str]]:
        if not raw_feed:
            return []

        parsed = feedparser.parse(raw_feed)
        entries: list[dict[str, str]] = []
        for entry in parsed.entries:
            entries.append(
                {
                    "title": str(getattr(entry, "title", "")),
                    "summary": str(getattr(entry, "summary", "")),
                    "link": str(getattr(entry, "link", "")),
                    "published": str(getattr(entry, "published", "")),
                }
            )
        return entries
