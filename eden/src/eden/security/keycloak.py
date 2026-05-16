"""Keycloak token verification (locked decision #8).

Cryptographic verification only: the RS256 signature is checked against
Keycloak's published JWKS (cached, rotated), plus issuer / audience / expiry.
The active tenant is read from a Keycloak-signed custom claim — NEVER from
the request body, query string or an unsigned header (spec #3 fail-safe).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import jwt
from jwt import PyJWKClient

from eden.config import get_settings

_settings = get_settings()

# PyJWKClient caches signing keys and refreshes on rotation/unknown kid.
_jwk_client = PyJWKClient(
    _settings.oidc_jwks_url,
    cache_keys=True,
    lifespan=_settings.oidc_jwks_ttl,
)


class TokenVerificationError(Exception):
    """Raised on any failure to cryptographically establish the caller."""


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    tenant_id: uuid.UUID
    email: str | None
    roles: frozenset[str]
    scopes: frozenset[str]
    raw: dict = field(repr=False)


def _extract_roles(payload: dict) -> frozenset[str]:
    roles: set[str] = set(payload.get("realm_access", {}).get("roles", []))
    for client in payload.get("resource_access", {}).values():
        roles.update(client.get("roles", []))
    return frozenset(roles)


def verify_token(token: str) -> TokenClaims:
    """Verify signature + claims and return the trusted token contents.

    Raises TokenVerificationError on ANY problem — callers must fail closed.
    """
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        payload: dict = jwt.decode(
            token,
            signing_key.key,
            algorithms=_settings.oidc_algorithms,
            audience=_settings.oidc_audience,
            issuer=_settings.oidc_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        raise TokenVerificationError(f"token verification failed: {exc}") from exc

    raw_tenant = payload.get(_settings.oidc_tenant_claim)
    if not raw_tenant:
        raise TokenVerificationError(
            f"token missing required signed tenant claim {_settings.oidc_tenant_claim!r}"
        )
    try:
        tenant_id = uuid.UUID(str(raw_tenant))
    except ValueError as exc:
        raise TokenVerificationError("tenant claim is not a valid UUID") from exc

    scope_str = payload.get("scope", "")
    return TokenClaims(
        subject=payload["sub"],
        tenant_id=tenant_id,
        email=payload.get("email"),
        roles=_extract_roles(payload),
        scopes=frozenset(scope_str.split()) if scope_str else frozenset(),
        raw=payload,
    )
