"""FastAPI DB dependencies.

`tenant_db` is the ONLY way a handler obtains a tenant-scoped session, and
it refuses to open one unless the tenant routing middleware has attached a
verified `AuthContext`. This is the enforcement point behind spec #3's
"connection must completely abort" guarantee.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from eden.db.session import control_session, tenant_session
from eden.security.principal import AuthContext


async def tenant_db(request: Request) -> AsyncIterator[AsyncSession]:
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if auth is None:
        # Defence in depth: never reachable past the middleware, but if it
        # ever were, abort rather than open an unscoped connection.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="no verified tenant context; refusing database connection",
        )
    async with tenant_session(auth.tenant_schema) as session:
        yield session


async def control_db() -> AsyncIterator[AsyncSession]:
    async with control_session() as session:
        yield session
