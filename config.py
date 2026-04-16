from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-based config. Uses DATABASE_URL from Railway or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str

    # Auth — set JWT_SECRET in production (e.g. long random string).
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # OAuth: audience / client ids from provider consoles (used to verify tokens).
    google_client_id: str | None = None
    apple_client_id: str | None = None


settings = Settings()
