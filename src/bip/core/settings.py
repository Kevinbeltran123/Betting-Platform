"""Global application settings loaded from environment variables."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with env var loading via pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # SUPABASE_DB_PASSWORD is read directly by verify scripts, not by Settings
    )

    supabase_url: str
    supabase_key: str
    parquet_base_path: str = "data/cache"
    model_dir: str = "models"  # Phase 2: root for model artifacts (models/{sport}/{league}/{version}/)
    api_football_key: str
    odds_api_key: str
    telegram_bot_token: str = ""
    log_level: str = "INFO"

    # ─────────────────────────────────────────────────────
    # Phase 3 additions (D-13, RESEARCH §Standard Stack)
    # PATTERNS.md drift risk #3: append flat fields to existing class — NO per-feature settings classes.
    # ─────────────────────────────────────────────────────
    telegram_channel_id: str = ""              # D-13: -100<id> format; validated below (Pitfall 8)
    anthropic_api_key: str = ""                # D-05: Anthropic API key for Role C validator
    claude_model: str = "claude-sonnet-4-6"    # D-05: current Sonnet alias (verified May 2026)
    max_kelly_fraction: float = 0.25           # PICK-02 / D-10: quarter Kelly default

    @field_validator("telegram_channel_id")
    @classmethod
    def _validate_channel_id(cls, v: str) -> str:
        """Pitfall 8: Telegram private channels are `-100<10-13 digits>`.

        Empty default allowed (tests / CI without secrets construct cleanly).
        When SET, must start with `-100` AND be at least 8 chars total.
        """
        if v == "":
            return v
        if not v.startswith("-100"):
            raise ValueError(
                f"telegram_channel_id must start with '-100' (got {v!r}). "
                "Forward a channel message to @userinfobot to read the correct ID."
            )
        if len(v) < 8:  # "-100" + at least 4 digits
            raise ValueError(
                f"telegram_channel_id appears truncated (got {v!r}, expected -100<10-13 digits>)."
            )
        return v
