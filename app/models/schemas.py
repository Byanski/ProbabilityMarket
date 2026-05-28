from pydantic import BaseModel, Field


class OutcomeValue(BaseModel):
    name: str
    price: float
    point: float | None = None


class MarketSnapshot(BaseModel):
    source_key: str
    source_title: str
    market_key: str
    outcomes: list[OutcomeValue]


class EventSnapshot(BaseModel):
    id: str
    sport_key: str
    commence_time: str
    home_team: str
    away_team: str
    markets: list[MarketSnapshot]


class StatsSnapshot(BaseModel):
    team_standings: list[dict] = Field(default_factory=list)
    historical_scores: list[dict] = Field(default_factory=list)
    player_availability: list[dict] = Field(default_factory=list)


class SourceCategory(BaseModel):
    key: str
    title: str


class IndexRow(BaseModel):
    id: str
    category_key: str
    category_title: str
    target_matchup: str
    market_favorite: str
    predicted_winner: str
    aggregated_mean_value: float
    highest_variance_vector: float
    adjustment_score: float
    normalized_probability: float
    prediction_confidence: float
    history_adjustment: float = 0.0
    home_away_adjustment: float = 0.0
    day_night_adjustment: float = 0.0
    prediction_notes: list[str] = Field(default_factory=list)
    source_count: int
    market_keys: list[str] = Field(default_factory=list)
    line_points: list[float] = Field(default_factory=list)
    telemetry_vectors: list[dict] = Field(default_factory=list)
    status: str = "live"


class DashboardPayload(BaseModel):
    status: str
    warnings: list[str]
    categories: list[SourceCategory]
    selected_category_key: str | None = None
    rows: list[IndexRow]
    stats: StatsSnapshot
