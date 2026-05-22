from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/llm_logs"

    # Redis
    redis_url: str = "redis://redis:6379"

    # LLM Providers
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # Ingestion service
    ingestion_service_url: str = "http://ingestion-service:8001"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # PII redaction
    pii_redaction_enabled: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
