"""Tenant routing middleware (spec #3 — the hard fail-safe).

Order of operations for every request to a protected path:

1. Extract the Bearer token.
2. **Cryptographically verify** it against Keycloak's JWKS (signature,
   issuer, audience, expiry) and read the signed tenant claim.
3. Resolve the tenant's `client_<uuid>` schema from `eden_control` and
   confirm it is provisioned + active.
4. Attach the verified `AuthContext` (incl. the resolved schema) to
   `request.state`.

If ANY step fails, the request is rejected here and **no tenant-bound
database connection is ever opened** — handlers obtain a DB session only
via `tenant_db()`, which requires the context this middleware sets. There
is no code path that reaches tenant data without a verified tenant.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from eden.config import get_settings
from eden.control.models.principal import Principal
from eden.control.models.tenant import SchemaStatus, Tenant, TenantSchema, TenantStatus
from eden.db.session import control_session
from eden.security.keycloak import TokenVerificationError, verify_token
from eden.security.principal import AuthContext

_settings = get_settings()

# Only these prefixes may be reached without a verified tenant context.
_PUBLIC_PREFIXES: tuple[str, ...] = ("/healthz", "/livez", "/readyz", "/docs", "/openapi.json", "/redoc")


def _abort(status_code: int, code: str, detail: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": code, "detail": detail, "request_id": request_id},
    )


class TenantRoutingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id

        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return _abort(401, "unauthenticated", "missing bearer token", request_id)
        token = auth_header[7:].strip()

        # (2) Cryptographic verification. No fallback — fail closed.
        try:
            claims = verify_token(token)
        except TokenVerificationError as exc:
            return _abort(401, "token_invalid", str(exc), request_id)

        # (3) Resolve the tenant schema AND the principal from the control
        #     plane in one session. Identity lives in Keycloak; the principals
        #     row is its control-plane projection (created by seed/onboarding,
        #     later SCIM). An authenticated-but-unregistered subject is
        #     rejected — fail closed, never auto-invent a principal.
        try:
            async with control_session() as session:
                row = (
                    await session.execute(
                        select(TenantSchema, Tenant)
                        .join(Tenant, Tenant.id == TenantSchema.tenant_id)
                        .where(TenantSchema.tenant_id == claims.tenant_id)
                    )
                ).first()
                principal = (
                    await session.execute(
                        select(Principal).where(
                            Principal.keycloak_sub == claims.subject
                        )
                    )
                ).scalar_one_or_none()
        except Exception:  # noqa: BLE001 - control-plane lookup must not leak details
            return _abort(503, "control_plane_unavailable", "tenant lookup failed", request_id)

        if row is None:
            return _abort(403, "tenant_unknown", "no schema for verified tenant", request_id)

        schema_row, tenant_row = row
        if (
            schema_row.status != SchemaStatus.ready
            or tenant_row.status != TenantStatus.active
        ):
            return _abort(
                403,
                "tenant_inactive",
                f"tenant not active (schema={schema_row.status}, tenant={tenant_row.status})",
                request_id,
            )

        if principal is None:
            return _abort(
                403, "principal_unregistered",
                "verified subject has no control-plane principal", request_id,
            )
        if not principal.is_active:
            return _abort(403, "principal_inactive", "principal is deactivated", request_id)

        # (4) Attach the verified context. Handlers/DB read ONLY from here.
        request.state.auth = AuthContext.from_claims(
            claims,
            principal_id=principal.id,
            tenant_schema=schema_row.schema_name,
            request_id=request_id,
            source_ip=request.client.host if request.client else None,
        )

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
