"""Test bootstrap: provide the env the typed Settings require so pure-logic
tests can import eden.* without a real DB or Keycloak.

The DB DSNs point at the INTEGRATION test server (port 5433): either the CI
postgres service or the cluster spawned by tests/integration/conftest.py.
Unit tests never open a connection, so for them the value is inert; using
one canonical DSN everywhere means the module-level engines (bound at first
eden import) are always pointed at the right server when integration tests
do connect.
"""

import os

os.environ.setdefault(
    "EDEN_DB_DSN", "postgresql+asyncpg://eden_app:eden_app_pw@127.0.0.1:5433/eden"
)
os.environ.setdefault(
    "EDEN_DB_ADMIN_DSN", "postgresql+asyncpg://eden_owner:eden_owner_pw@127.0.0.1:5433/eden"
)
os.environ.setdefault("EDEN_OIDC_ISSUER", "https://auth.test/realms/eden")
os.environ.setdefault(
    "EDEN_OIDC_JWKS_URL", "https://auth.test/realms/eden/protocol/openid-connect/certs"
)
os.environ.setdefault("EDEN_OIDC_AUDIENCE", "eden-api")
