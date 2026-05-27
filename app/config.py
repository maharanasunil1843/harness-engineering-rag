"""App-wide configuration loaded from .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    openai_api_key: str
    database_url: str
    supabase_url: str
    supabase_anon_key: str
    upstash_redis_rest_url: str
    upstash_redis_rest_token: str
    langsmith_api_key: str
    langsmith_project: str = "harness-rag-mvp"
    langsmith_tracing: bool = True
    planner_model: str = "claude-sonnet-4-6"
    worker_model: str = "claude-haiku-4-5"
    synthesizer_model: str = "claude-sonnet-4-6"
    embedding_model: str = "text-embedding-3-small"
    cache_similarity_threshold: float = 0.92
    cache_ttl: int = 3600
    rate_limit_rpm: int = 60
    rate_limit_window: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
