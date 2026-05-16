"""Test bootstrap: provide the env the typed Settings require so pure-logic
tests can import eden.* without a real DB or Keycloak."""

import os

os.environ.setdefault("EDEN_DB_DSN", "postgresql+asyncpg://eden_app:x@localhost:5432/eden")
os.environ.setdefault("EDEN_DB_ADMIN_DSN", "postgresql+asyncpg://eden_owner:x@localhost:5432/eden")
os.environ.setdefault("EDEN_OIDC_ISSUER", "https://auth.test/realms/eden")
os.environ.setdefault(
    "EDEN_OIDC_JWKS_URL", "https://auth.test/realms/eden/protocol/openid-connect/certs"
)
os.environ.setdefault("EDEN_OIDC_AUDIENCE", "eden-api")
