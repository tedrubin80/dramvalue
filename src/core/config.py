"""
Application configuration using Pydantic Settings.
All configuration is loaded from environment variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    app_name: str = "WTracker"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = Field(..., min_length=32)
    cors_origins: str = "https://dramvalue.com,https://www.dramvalue.com"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: PostgresDsn

    # -------------------------------------------------------------------------
    # JWT Authentication
    # -------------------------------------------------------------------------
    jwt_secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # -------------------------------------------------------------------------
    # Email (AWS SES)
    # -------------------------------------------------------------------------
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    email_from: EmailStr = "alerts@dramvalue.com"
    email_from_name: str = "DramValue"

    # -------------------------------------------------------------------------
    # Scraping
    # -------------------------------------------------------------------------
    scraper_user_agent: str = "WTracker/1.0"
    scraper_rate_limit_requests: int = 10
    scraper_rate_limit_period: int = 60
    scraper_respect_robots_txt: bool = True
    scraper_cache_enabled: bool = True
    scraper_cache_ttl_hours: int = 24

    # -------------------------------------------------------------------------
    # Admin
    # -------------------------------------------------------------------------
    admin_email: EmailStr = "ted@theorubin.com"

    # -------------------------------------------------------------------------
    # Private JSON Feed API (key-authenticated, for personal integrations)
    # -------------------------------------------------------------------------
    feed_api_key: str = Field(default="", description="API key for /api/v1/feed/* endpoints")

    # -------------------------------------------------------------------------
    # Trust & Fraud Detection
    # -------------------------------------------------------------------------
    trust_base_score: int = 50
    trust_verified_bonus: int = 25
    trust_submission_increment: int = 1
    fraud_stddev_threshold: float = 2.0
    fraud_new_account_submission_limit: int = 5
    fraud_burst_window_minutes: int = 10
    fraud_burst_limit: int = 3
    fraud_single_user_influence_cap: float = 0.25

    # -------------------------------------------------------------------------
    # Forecasting
    # -------------------------------------------------------------------------
    forecast_min_datapoints: int = 10
    forecast_confidence_threshold: float = 0.6
    forecast_recalculate_on_new_data: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
