"""Tenant schema provisioner + migration runner (P0 exit criteria #2 & #5).

Onboarding a tenant: create `client_<uuid>`, apply every versioned SQL
template under migrations/tenant_template/ in order, and record each
applied migration (with checksum) in eden_control so a failed tenant is
retried, not silently skipped. Idempotent: re-running skips already-applied
migrations and only fills gaps.

DDL runs on the privileged AUTOCOMMIT admin engine — never the pooled app
role (locked decision #10). After DDL, the app role is granted USAGE/DML on
the new schema so runtime requests can actually reach it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from eden.config import get_settings
from eden.control.models.tenant import (
    SchemaStatus,
    TenantSchema,
    TenantSchemaVersion,
)
from eden.db.session import (
    AppSessionFactory,
    admin_engine,
    assert_valid_tenant_schema,
)

_settings = get_settings()
_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "migrations" / "tenant_template"
_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")
# The app role name is config-controlled, but it is interpolated into DDL —
# validate it like any other identifier we refuse to bind-parameterize.
_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _ordered_templates() -> list[Path]:
    files = [p for p in _TEMPLATE_DIR.glob("*.sql") if _MIGRATION_RE.match(p.name)]
    return sorted(files, key=lambda p: p.name)


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


async def _run_ddl_script(schema: str, sql: str) -> None:
    """Run a multi-statement SQL script inside `schema`.

    SQLAlchemy's asyncpg dialect routes text() through prepared statements,
    which reject multi-command strings — so migration templates (many
    statements, DO $$ blocks) must go through asyncpg's simple-query
    protocol, i.e. the raw driver connection. The simple protocol also runs
    the whole script in ONE implicit transaction, so a failed template
    leaves no half-applied tenant schema behind.
    """
    async with admin_engine.connect() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection  # asyncpg.Connection
        try:
            await driver.execute(f'SET search_path = "{schema}";\n{sql}')
        finally:
            # Pool hygiene: plain SET survives the implicit transaction.
            await driver.execute("RESET search_path")


async def _grant_app_role(schema: str) -> None:
    """Grant the pooled app role USAGE + DML on a freshly provisioned schema.

    Locked decision #10: eden_app owns nothing and cannot CREATE; the
    provisioner (running as eden_owner) grants per-schema access at
    provision time. Default privileges cover tables added by later template
    migrations. Skipped when the role does not exist (bare test databases).
    """
    role = _settings.db_app_role
    if not _ROLE_RE.fullmatch(role):
        raise ValueError(f"refusing unsafe app role identifier: {role!r}")
    grants = f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
        GRANT USAGE ON SCHEMA "{schema}" TO {role};
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON ALL TABLES IN SCHEMA "{schema}" TO {role};
        GRANT USAGE, SELECT
            ON ALL SEQUENCES IN SCHEMA "{schema}" TO {role};
        ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}"
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role};
        ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}"
            GRANT USAGE, SELECT ON SEQUENCES TO {role};
    END IF;
END $$;
"""
    async with admin_engine.connect() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.execute(grants)


async def provision_tenant(tenant_id: str) -> str:
    """Create + migrate the schema for `tenant_id`. Returns the schema name."""
    schema = assert_valid_tenant_schema(_settings.tenant_schema_name(tenant_id))

    async with AppSessionFactory() as ctl, ctl.begin():
        await ctl.execute(text(f'SET LOCAL search_path = "{_settings.control_schema}"'))
        ts = (
            await ctl.execute(
                select(TenantSchema).where(TenantSchema.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if ts is None:
            ts = TenantSchema(
                tenant_id=tenant_id, schema_name=schema, status=SchemaStatus.provisioning
            )
            ctl.add(ts)
        else:
            ts.status = SchemaStatus.provisioning

    try:
        # (1) Create the schema (idempotent).
        async with admin_engine.connect() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

        # (2) Apply each template that has not yet succeeded for this tenant.
        for path in _ordered_templates():
            migration_id = path.stem
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)

            async with AppSessionFactory() as ctl, ctl.begin():
                await ctl.execute(
                    text(f'SET LOCAL search_path = "{_settings.control_schema}"')
                )
                already = (
                    await ctl.execute(
                        select(TenantSchemaVersion).where(
                            TenantSchemaVersion.tenant_id == tenant_id,
                            TenantSchemaVersion.migration_id == migration_id,
                            TenantSchemaVersion.succeeded.is_(True),
                        )
                    )
                ).scalar_one_or_none()
            if already is not None:
                continue

            await _run_ddl_script(schema, sql)

            async with AppSessionFactory() as ctl, ctl.begin():
                await ctl.execute(
                    text(f'SET LOCAL search_path = "{_settings.control_schema}"')
                )
                ctl.add(
                    TenantSchemaVersion(
                        tenant_id=tenant_id,
                        migration_id=migration_id,
                        checksum=checksum,
                        succeeded=True,
                    )
                )

        # (3) Grant the pooled app role access to the new schema.
        await _grant_app_role(schema)

        async with AppSessionFactory() as ctl, ctl.begin():
            await ctl.execute(text(f'SET LOCAL search_path = "{_settings.control_schema}"'))
            ts = (
                await ctl.execute(
                    select(TenantSchema).where(TenantSchema.tenant_id == tenant_id)
                )
            ).scalar_one()
            ts.status = SchemaStatus.ready
            ts.provisioned_at = datetime.now(timezone.utc).isoformat()
        return schema

    except Exception as exc:  # noqa: BLE001 - record failure for retry then re-raise
        async with AppSessionFactory() as ctl, ctl.begin():
            await ctl.execute(text(f'SET LOCAL search_path = "{_settings.control_schema}"'))
            ts = (
                await ctl.execute(
                    select(TenantSchema).where(TenantSchema.tenant_id == tenant_id)
                )
            ).scalar_one()
            ts.status = SchemaStatus.failed
            ts.last_error = str(exc)
        raise


async def migrate_all_tenants() -> dict[str, str]:
    """Apply pending tenant-template migrations to every provisioned schema.
    Returns {schema: 'ok' | 'error: ...'} so a failed tenant is visible."""
    async with AppSessionFactory() as ctl, ctl.begin():
        await ctl.execute(text(f'SET LOCAL search_path = "{_settings.control_schema}"'))
        tenant_ids = list(
            (await ctl.execute(select(TenantSchema.tenant_id))).scalars()
        )

    results: dict[str, str] = {}
    for tid in tenant_ids:
        try:
            schema = await provision_tenant(str(tid))
            results[schema] = "ok"
        except Exception as exc:  # noqa: BLE001
            results[_settings.tenant_schema_name(str(tid))] = f"error: {exc}"
    return results
