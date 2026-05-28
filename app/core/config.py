from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from .env and process environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telemetry_api_host: str | None = Field(default=None, alias="TELEMETRY_API_HOST")
    telemetry_api_key: str | None = Field(default=None, alias="TELEMETRY_API_KEY")
    telemetry_default_region: str = Field(default="us", alias="TELEMETRY_DEFAULT_REGION")
    telemetry_data_format: str = Field(default="american", alias="TELEMETRY_DATA_FORMAT")

    legacy_data_feed_url_primary: str | None = Field(default=None, alias="DATA_FEED_URL_PRIMARY")
    legacy_data_feed_api_key: str | None = Field(default=None, alias="DATA_FEED_API_KEY")
    stats_feed_url: str | None = Field(default=None, alias="STATS_FEED_URL")
    news_feed_url: str | None = Field(default=None, alias="NEWS_FEED_URL")

    request_timeout_seconds: float = Field(default=8.0, alias="REQUEST_TIMEOUT_SECONDS")
    poll_interval_seconds: int = Field(default=30, alias="POLL_INTERVAL_SECONDS")
    baseline_margin: float = Field(default=0.045, alias="BASELINE_MARGIN")

    @property
    def missing_external_config(self) -> list[str]:
        required = {
            "TELEMETRY_API_HOST": self.resolved_telemetry_api_host,
            "TELEMETRY_API_KEY": self.resolved_telemetry_api_key,
            "STATS_FEED_URL": self.stats_feed_url,
            "NEWS_FEED_URL": self.news_feed_url,
        }
        placeholders = ("example.com", "your_secured_token_here")
        return [
            name
            for name, value in required.items()
            if not value or any(placeholder in value for placeholder in placeholders)
        ]

    @property
    def resolved_telemetry_api_host(self) -> str | None:
        if self.telemetry_api_host:
            return self.telemetry_api_host.rstrip("/")
        if self.legacy_data_feed_url_primary and "/v4/" in self.legacy_data_feed_url_primary:
            return self.legacy_data_feed_url_primary.split("/v4/", maxsplit=1)[0].rstrip("/")
        return None

    @property
    def resolved_telemetry_api_key(self) -> str | None:
        return self.telemetry_api_key or self.legacy_data_feed_api_key

    @property
    def telemetry_configured(self) -> bool:
        missing = set(self.missing_external_config)
        return "TELEMETRY_API_HOST" not in missing and "TELEMETRY_API_KEY" not in missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
