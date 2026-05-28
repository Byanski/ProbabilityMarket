from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
        score_history: list[dict] | None = None,
    ) -> list[IndexRow]:
        return [
            self._build_row(event, news_entries, category_lookup or {}, score_history or [])
            for event in events
        ]

    def _build_row(
        self,
        event: EventSnapshot,
        news_entries: list[dict[str, str]],
        category_lookup: dict[str, SourceCategory],
        score_history: list[dict],
    ) -> IndexRow:
        values = self._extract_prices(event)
        mean_value = round(fmean(values), 4) if values else 0.0
        news_shift = self.calculate_news_adjustment(event, news_entries)
        prediction = self._prediction_for_event(event, score_history, news_shift)

        category = category_lookup.get(event.sport_key)
        return IndexRow(
            id=event.id,
            category_key=event.sport_key,
            category_title=category.title if category else self._category_title_for_event(event),
            target_matchup=f"{event.away_team} at {event.home_team}",
            market_favorite=prediction["market_favorite"],
            predicted_winner=prediction["predicted_winner"],
            aggregated_mean_value=mean_value,
            highest_variance_vector=round(self.highest_variance_vector(values), 4),
            adjustment_score=round(news_shift, 4),
            normalized_probability=round(prediction["probability"], 4),
            prediction_confidence=round(prediction["confidence"], 4),
            history_adjustment=round(prediction["history_adjustment"], 4),
            home_away_adjustment=round(prediction["home_away_adjustment"], 4),
            day_night_adjustment=round(prediction["day_night_adjustment"], 4),
            prediction_notes=prediction["notes"],
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

    def _prediction_for_event(self, event: EventSnapshot, score_history: list[dict], news_shift: float) -> dict:
        market_probabilities = self._normalized_h2h_probabilities(event)
        if not market_probabilities:
            fallback = self.calculate_normalized_base_probability(self._extract_prices(event))
            return {
                "market_favorite": event.home_team,
                "predicted_winner": event.home_team,
                "probability": max(fallback - self.baseline_margin + news_shift, 0.0),
                "confidence": 0.5,
                "history_adjustment": 0.0,
                "home_away_adjustment": 0.0,
                "day_night_adjustment": 0.0,
                "notes": ["No head-to-head Source vectors available; using neutral fallback."],
            }

        market_favorite = max(market_probabilities, key=market_probabilities.get)
        home_adjustments = {event.home_team: 0.015, event.away_team: -0.005}
        history_adjustments = {
            team: self._recent_history_adjustment(team, score_history)
            for team in (event.home_team, event.away_team)
        }
        day_night_adjustments = {
            team: self._day_night_adjustment(team, event.commence_time, score_history)
            for team in (event.home_team, event.away_team)
        }

        adjusted: dict[str, float] = {}
        for team, probability in market_probabilities.items():
            adjusted[team] = probability - self.baseline_margin
            adjusted[team] += home_adjustments.get(team, 0.0)
            adjusted[team] += history_adjustments.get(team, 0.0)
            adjusted[team] += day_night_adjustments.get(team, 0.0)
            if team in (event.home_team, event.away_team):
                adjusted[team] += news_shift
            adjusted[team] = min(max(adjusted[team], 0.01), 0.99)

        total = sum(adjusted.values()) or 1.0
        normalized = {team: value / total for team, value in adjusted.items()}
        predicted_winner = max(normalized, key=normalized.get)
        ordered = sorted(normalized.values(), reverse=True)
        edge = ordered[0] - (ordered[1] if len(ordered) > 1 else 0.5)
        source_count = len({market.source_key for market in event.markets if market.market_key == "h2h"})

        return {
            "market_favorite": market_favorite,
            "predicted_winner": predicted_winner,
            "probability": normalized[predicted_winner],
            "confidence": min(max(0.5 + edge + min(source_count, 10) * 0.01, 0.0), 0.99),
            "history_adjustment": history_adjustments.get(predicted_winner, 0.0),
            "home_away_adjustment": home_adjustments.get(predicted_winner, 0.0),
            "day_night_adjustment": day_night_adjustments.get(predicted_winner, 0.0),
            "notes": [
                f"Market favorite from h2h Source consensus: {market_favorite}.",
                f"Recent history window includes {len(score_history)} completed or scheduled data points.",
                f"Home/away and day/night modifiers are intentionally small versus market consensus.",
            ],
        }

    def _normalized_h2h_probabilities(self, event: EventSnapshot) -> dict[str, float]:
        by_team: dict[str, list[float]] = {}
        for market in event.markets:
            if market.market_key != "h2h":
                continue
            source_probs = {
                outcome.name: self._implied_probability(outcome.price)
                for outcome in market.outcomes
                if outcome.name in (event.home_team, event.away_team) and outcome.price != 0
            }
            total = sum(source_probs.values())
            if total <= 0:
                continue
            for team, probability in source_probs.items():
                by_team.setdefault(team, []).append(probability / total)

        return {team: fmean(probabilities) for team, probabilities in by_team.items() if probabilities}

    def _recent_history_adjustment(self, team: str, score_history: list[dict]) -> float:
        games = [
            game
            for game in score_history
            if isinstance(game, dict) and self._score_for_team(game, team) is not None
        ]
        if not games:
            return 0.0

        wins = 0
        margins: list[float] = []
        for game in games:
            team_score = self._score_for_team(game, team)
            opponent_scores = [
                self._coerce_score(score.get("score"))
                for score in game.get("scores", [])
                if isinstance(score, dict) and score.get("name") != team
            ]
            opponent_scores = [score for score in opponent_scores if score is not None]
            if team_score is None or not opponent_scores:
                continue
            margin = team_score - opponent_scores[0]
            margins.append(margin)
            wins += int(margin > 0)

        if not margins:
            return 0.0

        win_rate = wins / len(margins)
        margin_signal = max(min(fmean(margins) / 100.0, 0.03), -0.03)
        return max(min((win_rate - 0.5) * 0.06 + margin_signal, 0.06), -0.06)

    def _day_night_adjustment(self, team: str, commence_time: str, score_history: list[dict]) -> float:
        target_bucket = self._time_bucket(commence_time)
        bucket_games = [
            game
            for game in score_history
            if isinstance(game, dict)
            and self._time_bucket(str(game.get("commence_time", ""))) == target_bucket
            and self._score_for_team(game, team) is not None
        ]
        if len(bucket_games) < 2:
            return 0.0

        wins = 0
        played = 0
        for game in bucket_games:
            team_score = self._score_for_team(game, team)
            opponent_scores = [
                self._coerce_score(score.get("score"))
                for score in game.get("scores", [])
                if isinstance(score, dict) and score.get("name") != team
            ]
            opponent_scores = [score for score in opponent_scores if score is not None]
            if team_score is None or not opponent_scores:
                continue
            wins += int(team_score > opponent_scores[0])
            played += 1
        if played < 2:
            return 0.0
        return max(min((wins / played - 0.5) * 0.03, 0.03), -0.03)

    def _score_for_team(self, game: dict, team: str) -> float | None:
        scores = game.get("scores") or []
        for score in scores:
            if isinstance(score, dict) and score.get("name") == team:
                return self._coerce_score(score.get("score"))
        return None

    def _coerce_score(self, value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _time_bucket(self, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "unknown"
        return "day" if 10 <= parsed.hour < 18 else "night"

    def _category_title_for_event(self, event: EventSnapshot) -> str:
        sport_key = event.sport_key.lower()
        if "basketball" in sport_key or "nba" in sport_key:
            return "Category Alpha"
        if "football" in sport_key or "nfl" in sport_key:
            return "Category Beta"
        return "Category Gamma"
