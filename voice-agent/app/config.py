from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    encryption_key: str
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    retell_api_key: str = ""
    retell_webhook_secret: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
