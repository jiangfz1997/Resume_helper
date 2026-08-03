from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://admin:password123@localhost:5432/resume_db"

    jwt_secret_key: str = _DEFAULT_JWT_SECRET
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

    # Browser origins allowed to call the API. Wildcards are rejected because
    # the CORS middleware runs with allow_credentials=True.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # When set, LangGraph pipelines route through LangGraph Studio Server
    # so executions appear as live animations in Studio.
    # Start Studio with: langgraph dev
    langgraph_studio_url: str | None = None

    @model_validator(mode="after")
    def _check_production_hardening(self) -> "Settings":
        if self.debug:
            return self
        if self.jwt_secret_key == _DEFAULT_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET_KEY still holds its default value while DEBUG=false. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins while DEBUG=false; '*' is not allowed "
                "because credentials are sent with cross-origin requests."
            )
        return self


settings = Settings()
