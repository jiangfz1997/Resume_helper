from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://admin:password123@localhost:5432/resume_db"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:14b"
    ollama_temperature: float = 0.3

    pipeline_initial_threshold: float = 0.8
    pipeline_decay_per_retry: float = 0.05
    pipeline_min_threshold: float = 0.6
    pipeline_max_retries: int = 3

    admin_emails: list[str] = []

    debug: bool = True

    # When set, LangGraph pipelines route through LangGraph Studio Server
    # so executions appear as live animations in Studio.
    # Start Studio with: langgraph dev
    langgraph_studio_url: str | None = None


settings = Settings()
