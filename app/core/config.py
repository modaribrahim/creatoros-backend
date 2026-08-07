from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = (
        "postgresql+asyncpg://creatoros:creatoros@localhost:5432/creatoros"
    )
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    youtube_api_key: str = ""
    embed_model: str = "openai/text-embedding-3-small"
    analyze_api_key: str = ""
    analyze_base_url: str = "https://api.mixroute.ai/v1"
    analyze_model: str = "deepseek-v4-flash"
    embedding_dim: int = 1536
    chunk_size: int = 50
    max_concurrency: int = 4
    redis_url: str = "redis://localhost:6379/0"
    max_comments: int = 300
    max_replies_per_thread: int = 50
    like_change_pct: float = 0.2

    jwt_secret: str = "dev-only-change-me-to-a-long-random-string-32-bytes"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30
    frontend_url: str = "http://localhost:5173"
    verification_token_ttl_hours: int = 24
    resend_api_key: str = ""
    resend_from: str = "CreatorOS <onboarding@resend.dev>"

    chat_model: str = "deepseek-v4-flash"
    chat_tool_limit: int = 8
    chat_rag_limit: int = 8

    auto_create_tables: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
