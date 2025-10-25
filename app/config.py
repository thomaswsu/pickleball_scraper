"""Configuration handling for the pickleball scraper."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    rec_base_url: str = "https://api.rec.us"
    organization_slug: str = "san-francisco-rec-park"
    scrape_interval_seconds: int = 300
    http_timeout_seconds: int = 30
    timezone: str = "America/Los_Angeles"
    database_url: str = "sqlite:///./app.db"
    scraper_enabled: bool = True
    pickleball_sport_id: str | None = "bd745b6e-1dd6-43e2-a69f-06f094808a96"
    smtp_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str = "alerts@example.com"
    smtp_use_tls: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
