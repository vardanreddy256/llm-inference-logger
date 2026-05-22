from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/llm_logs"
    redis_url: str = "redis://redis:6379"
    log_level: str = "INFO"
    consumer_group: str = "ingestion-group"
    consumer_name: str = "ingestion-consumer-1"
    stream_name: str = "inference_events"
    batch_size: int = 50
    poll_interval_ms: int = 500

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
