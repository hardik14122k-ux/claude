"""Request-scoped security context, attached to request.state by the tenant
router after the token is cryptographically verified. Handlers and the PDP
read ONLY from here — never from raw request input."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request

from eden.security.keycloak import TokenClaims


@dataclass(frozen=True, slots=True)
class AuthContext:
    keycloak_sub: str
    tenant_id: uuid.UUID
    tenant_schema: str
    email: str | None
    roles: frozenset[str]
    scopes: frozenset[str]
    request_id: str
    source_ip: str | None

    @classmethod
    def from_claims(
        cls,
        claims: TokenClaims,
        *,
        tenant_schema: str,
        request_id: str,
        source_ip: str | None,
    ) -> "AuthContext":
        return cls(
            keycloak_sub=claims.subject,
            tenant_id=claims.tenant_id,
            tenant_schema=tenant_schema,
            email=claims.email,
            roles=claims.roles,
            scopes=claims.scopes,
            request_id=request_id,
            source_ip=source_ip,
        )


def get_auth(request: Request) -> AuthContext:
    """FastAPI dependency: the verified context, or 401 if routing did not set it."""
    from fastapi import HTTPException, status

    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthenticated: no verified security context",
        )
    return auth
