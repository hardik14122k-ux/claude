"""Typed application settings (pydantic-settings). Single source of truth."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EDEN_", env_file=".env", extra="ignore")

    env: str = "local"
    region: str = "ap-south-1"  # India only (DPDP-aligned) — locked decision #9
    log_level: str = "INFO"

    # Database — one pooled application role (locked decision #10).
    db_dsn: str
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 10
    # Privileged DSN for DDL only (Alembic + provisioner).
    db_admin_dsn: str
    # The pooled application role. The provisioner grants it USAGE/DML per
    # schema (locked decision #10: it never owns schemas or runs DDL).
    db_app_role: str = "eden_app"

    # Keycloak (self-hosted) — locked decision #8.
    oidc_issuer: str
    oidc_jwks_url: str
    oidc_audience: str
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    oidc_tenant_claim: str = "eden_tenant"
    oidc_jwks_ttl: int = 3600

    # Hard fail-safe: tenant routing aborts the DB connection on any doubt.
    fail_closed: bool = True

    @property
    def control_schema(self) -> str:
        return "eden_control"

    @staticmethod
    def tenant_schema_name(tenant_id: str) -> str:
        """Deterministic schema name for a client tenant: client_<uuid-no-dashes>."""
        return f"client_{str(tenant_id).replace('-', '')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
