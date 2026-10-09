from pydantic_settings import BaseSettings
from functools import lru_cache
from pydantic import Field


class Settings(BaseSettings):
    # Google Calendar
    google_calendar_id: str = Field(default="primary")
    google_credentials_file: str = Field(default="credentials.json")
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")

    # Service
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    backend_api_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
