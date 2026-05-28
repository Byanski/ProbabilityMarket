from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from app.models.schemas import EventSnapshot, IndexRow, SourceCategory


@dataclass(frozen=True)
class AnalyticsProcessor:
    """Transforms parsed market data and news text into dashboard index rows.

    Processing steps:
    1. Flatten all extracted outcome prices for an event into a numerical array.
    2. Convert values into implied probabilities using either American or decimal
       source formatting, then average the result.
    3. Subtract the configured source baseline margin from that normalized base.
    4. Compute the highest variance vector as the spread between the highest and
       lowest individual source prices in the event.
    5. Scan synchronized news text for availability indicators. When matched,
       shift the final index distribution by a deterministic -5% to -15% based
       on indicator severity.
    """

    baseline_margin: float = 0.045
    data_format: str = "american"
    negative_indicators: tuple[str, ...] = ("injured", "out", "sidelined", "suspended")

    def build_index_rows(
        self,
        events: list[EventSnapshot],
        news_entries: list[dict[str, str]],
        category_lookup: dict[str, SourceCategory] | None = None,
    ) -> list[IndexRow]:
        return [self._build_row(event, news_entries, category_lookup or {}) for event in events]

    def _build_row(
        self,
        event: EventSnapshot,
        news_entries: list[dict[str, str]],
        category_lookup: dict[str, SourceCategory],
    ) -> IndexRow:
        values = self._extract_prices(event)
        mean_value = round(fmean(values), 4) if values else 0.0
        normalized_probability = self.calculate_normalized_base_probability(values)
        margin_adjusted_probability = max(normalized_probability - self.baseline_margin, 0.0)
        news_shift = self.calculate_news_adjustment(event, news_entries)
        final_probability = max(margin_adjusted_probability + news_shift, 0.0)

        category = category_lookup.get(event.sport_key)
        return IndexRow(
            id=event.id,
            category_key=event.sport_key,
            category_title=category.title if category else self._category_title_for_event(event),
            target_matchup=f"{event.away_team} at {event.home_team}",
            aggregated_mean_value=mean_value,
            highest_variance_vector=round(self.highest_variance_vector(values), 4),
            adjustment_score=round(news_shift, 4),
            normalized_probability=round(final_probability, 4),
            source_count=len({market.source_key for market in event.markets}),
            market_keys=sorted({market.market_key for market in event.markets}),
            line_points=sorted({outcome.point for market in event.markets for outcome in market.outcomes if outcome.point is not None}),
            telemetry_vectors=self._telemetry_vectors(event),
        )

    def calculate_normalized_base_probability(self, values: list[float]) -> float:
        implied = [self._implied_probability(value) for value in values if value != 0]
        if not implied:
            return 0.0
        return min(max(fmean(implied), 0.0), 1.0)

    def highest_variance_vector(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        return max(values) - min(values)

    def calculate_news_adjustment(self, event: EventSnapshot, news_entries: list[dict[str, str]]) -> float:
        haystack = self._event_news_text(event, news_entries)
        matched = [indicator for indicator in self.negative_indicators if indicator in haystack]
        if not matched:
            return 0.0

        severity = min(len(matched), 3)
        return -0.05 * severity

    def _extract_prices(self, event: EventSnapshot) -> list[float]:
        return [outcome.price for market in event.markets for outcome in market.outcomes]

    def _event_news_text(self, event: EventSnapshot, news_entries: list[dict[str, str]]) -> str:
        aliases = (event.home_team.lower(), event.away_team.lower())
        relevant_chunks: list[str] = []
        for entry in news_entries:
            text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
            if any(alias and alias in text for alias in aliases):
                relevant_chunks.append(text)
        return " ".join(relevant_chunks)

    def _telemetry_vectors(self, event: EventSnapshot) -> list[dict]:
        vectors: list[dict] = []
        for market in event.markets:
            for outcome in market.outcomes:
                vectors.append(
                    {
                        "source_key": market.source_key,
                        "source_title": market.source_title,
                        "market_key": market.market_key,
                        "name": outcome.name,
                        "price": outcome.price,
                        "point": outcome.point,
                    }
                )
        return vectors

    def _implied_probability(self, value: float) -> float:
        if self.data_format.lower() == "american":
            if value > 0:
                return 100.0 / (value + 100.0)
            return abs(value) / (abs(value) + 100.0)
        if value > 0:
            return 1.0 / value
        return 0.0

    def _category_title_for_event(self, event: EventSnapshot) -> str:
        sport_key = event.sport_key.lower()
        if "basketball" in sport_key or "nba" in sport_key:
            return "Category Alpha"
        if "football" in sport_key or "nfl" in sport_key:
            return "Category Beta"
        return "Category Gamma"
