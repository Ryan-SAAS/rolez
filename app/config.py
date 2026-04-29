from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/rolez.sqlite3",
        description="SQLAlchemy async URL. Railway injects DATABASE_URL as postgresql://… — we rewrite to asyncpg.",
    )

    rolez_admin_api_key: str = Field(default="dev-admin-api-key", alias="ROLEZ_ADMIN_API_KEY")

    admin_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["https://tech.startanaicompany.com"],
        alias="ADMIN_ALLOWED_ORIGINS",
    )

    metrics_user: str = Field(default="metrics", alias="METRICS_USER")
    metrics_pass: str = Field(default="change-me", alias="METRICS_PASS")

    skillz_api_url: str = Field(default="https://skillz.startanaicompany.com", alias="SKILLZ_API_URL")
    skillz_token: str = Field(default="", alias="SKILLZ_TOKEN")
    agentz_api_url: str = Field(default="https://agentz.startanaicompany.com", alias="AGENTZ_API_URL")
    agentz_token: str = Field(default="", alias="AGENTZ_TOKEN")

    mcp_orchestrator_url: str = Field(
        default="https://tech.startanaicompany.com/api/mcp",
        alias="MCP_ORCHESTRATOR_URL",
    )
    rolez_auth_ttl_seconds: int = Field(default=60, alias="ROLEZ_AUTH_TTL_SECONDS")

    public_url: str = Field(default="http://localhost:8000", alias="ROLEZ_PUBLIC_URL")
    port: int = Field(default=8000, alias="PORT")

    @field_validator("admin_allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, v):
        if isinstance(v, str) and v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://") :]
        if isinstance(v, str) and v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://") :]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
