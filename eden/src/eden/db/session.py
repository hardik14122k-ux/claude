"""Engines and request-scoped sessions.

Locked decision #10: the application connects with ONE pooled, low-privilege
role. The tenant router selects the active client schema with
``SET LOCAL search_path`` inside a per-request transaction. ``SET LOCAL`` is
transaction-scoped, so when the unit of work commits or rolls back the
search_path is discarded automatically — a pooled connection can never carry
one tenant's search_path into another tenant's request. (Plain ``SET`` is
NOT transactional and would leak across pooled requests; ``DISCARD ALL``
cannot run inside a transaction — hence ``SET LOCAL``.)

A separate privileged engine (`admin_engine`, AUTOCOMMIT) is used ONLY for
DDL by Alembic and the schema provisioner.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from eden.config import get_settings

_settings = get_settings()

# Tenant schema names are machine-generated as client_<32 hex>. Identifiers
# cannot be bound parameters, so we still validate before interpolating into
# SET LOCAL search_path — defence in depth against SQL injection.
_SCHEMA_RE = re.compile(r"^client_[0-9a-f]{32}$")
_CONTROL_SCHEMA = _settings.control_schema

engine = create_async_engine(
    _settings.db_dsn,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_timeout=_settings.db_pool_timeout,
    pool_pre_ping=True,
)
admin_engine = create_async_engine(_settings.db_admin_dsn, isolation_level="AUTOCOMMIT")

AppSessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
AdminSessionFactory = async_sessionmaker(admin_engine, expire_on_commit=False, class_=AsyncSession)


def assert_valid_tenant_schema(schema: str) -> str:
    if not _SCHEMA_RE.fullmatch(schema):
        # Fail closed: an unexpected schema identifier must never reach the DB.
        raise ValueError(f"refusing unsafe tenant schema identifier: {schema!r}")
    return schema


@asynccontextmanager
async def control_session() -> AsyncIterator[AsyncSession]:
    """Unit-of-work session pinned to the shared control plane (no tenant data)."""
    async with AppSessionFactory() as session:
        async with session.begin():
            await session.execute(text(f'SET LOCAL search_path = "{_CONTROL_SCHEMA}"'))
            yield session


@asynccontextmanager
async def tenant_session(schema: str) -> AsyncIterator[AsyncSession]:
    """Unit-of-work session scoped to one client schema.

    Order matters: the tenant schema is first so unqualified domain tables
    resolve there; ``eden_control`` follows for shared lookups. The
    transaction commits on clean exit and rolls back on error; ``SET LOCAL``
    guarantees the search_path dies with the transaction.
    """
    assert_valid_tenant_schema(schema)
    async with AppSessionFactory() as session:
        async with session.begin():
            await session.execute(
                text(f'SET LOCAL search_path = "{schema}", "{_CONTROL_SCHEMA}"')
            )
            yield session
