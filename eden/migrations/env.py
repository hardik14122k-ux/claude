"""Alembic environment for the eden_control schema ONLY.

Per-client tenant schemas are provisioned/migrated by
eden.provisioning.schema_provisioner from migrations/tenant_template/ —
they are intentionally NOT managed by Alembic.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from eden.config import get_settings
from eden.db.base import ControlBase

# Import all control models so their tables register on the metadata.
import eden.control.models  # noqa: F401

config = context.config
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.db_admin_dsn)

target_metadata = ControlBase.metadata
CONTROL_SCHEMA = _settings.control_schema


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    # Only manage objects in the control schema.
    if type_ == "table":
        return obj.schema == CONTROL_SCHEMA
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_settings.db_admin_dsn,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        version_table_schema=CONTROL_SCHEMA,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=CONTROL_SCHEMA,
        include_object=_include_object,
    )
    with context.begin_transaction():
        connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{CONTROL_SCHEMA}"')
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
