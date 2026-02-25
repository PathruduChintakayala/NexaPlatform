from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Nexa API"
    app_env: str = "local"
    app_debug: bool = True
    api_port: int = 8000
    database_url: str = "postgresql+psycopg://nexa:nexa@postgres:5432/nexa"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "replace-me"
    jwt_algorithm: str = "HS256"
    auto_run_jobs: bool = False
    auto_run_workflow_jobs: bool = False
    workflow_max_depth: int = 3
    workflow_max_actions: int = 20
    workflow_max_set_field: int = 10
    rate_limit_disabled: bool = False
    rate_limit_crm_mutations_per_minute: int = 60
    metrics_enabled: bool = False
    otel_enabled: bool = False
    authz_policy_backend: str = "auto"
    authz_default_allow: bool = True
    revenue_post_to_ledger: bool = False
    billing_post_to_ledger: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
