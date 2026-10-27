from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "PulseGuard AI"
    debug: bool = True
    groq_api_key: str = ""
    database_url: str = "sqlite:///./pulseguard.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()