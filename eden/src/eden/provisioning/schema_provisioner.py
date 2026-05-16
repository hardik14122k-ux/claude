"""Tenant schema provisioner + migration runner (P0 exit criteria #2 & #5).

Onboarding a tenant: create `client_<uuid>`, apply every versioned SQL
template under migrations/tenant_template/ in order, and record each
applied migration (with checksum) in eden_control so a failed tenant is
retried, not silently skipped. Idempotent: re-running skips already-applied
migrations and only fills gaps.

DDL runs on the privileged AUTOCOMMIT admin engine — never the pooled app
role (locked decision #10).
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
from eden.db.session import AdminSessionFactory, AppSessionFactory, assert_valid_tenant_schema

_settings = get_settings()
_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "migrations" / "tenant_template"
_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")


def _ordered_templates() -> list[Path]:
    files = [p for p in _TEMPLATE_DIR.glob("*.sql") if _MIGRATION_RE.match(p.name)]
    return sorted(files, key=lambda p: p.name)


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


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
        async with AdminSessionFactory() as admin:
            await admin.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

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

            async with AdminSessionFactory() as admin:
                await admin.execute(text(f'SET search_path = "{schema}"'))
                await admin.execute(text(sql))

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
