"""Global application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with env var loading via pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    supabase_url: str
    supabase_key: str
    parquet_base_path: str = "data/cache"
    api_football_key: str
    odds_api_key: str
    telegram_bot_token: str = ""
    log_level: str = "INFO"
