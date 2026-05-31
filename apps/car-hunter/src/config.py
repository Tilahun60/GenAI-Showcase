"""Application configuration using Pydantic Settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    db_url: str = Field(
        default="postgresql+asyncpg://carhunter:carhunter@localhost:5432/carhunter",
        description="Async PostgreSQL connection URL",
    )

    # Telegram
    telegram_bot_token: str = Field(default="", description="Telegram Bot API token")
    telegram_chat_id: str = Field(default="", description="Telegram chat/channel ID")

    # Gmail
    gmail_user: str = Field(default="", description="Gmail sender address")
    gmail_app_password: str = Field(default="", description="Gmail App Password")
    gmail_to: str = Field(default="", description="Recipient email address")

    # Discord
    discord_webhook_url: str = Field(default="", description="Discord webhook URL")

    # Scheduler
    scrape_interval_minutes: int = Field(default=30, ge=5, description="Scraping interval in minutes")

    # Car requirements
    max_price_pln: float = Field(default=60_000.0, description="Maximum car price in PLN")
    min_year: int = Field(default=2020, description="Minimum manufacture year")
    max_mileage_km: int = Field(default=150_000, description="Maximum mileage in km")

    # Alerting
    alert_score_threshold: float = Field(default=6.0, ge=0.0, le=10.0, description="Minimum score to alert")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def gmail_enabled(self) -> bool:
        return bool(self.gmail_user and self.gmail_app_password and self.gmail_to)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
