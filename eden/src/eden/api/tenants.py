"""Control-plane tenant onboarding (P0 exit criteria #2).

Creating a tenant registers it in `eden_control` and provisions its
dedicated `client_<uuid>` schema from the versioned SQL template. Gated by
`tenants:provision` (platform/consultancy-owner only).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eden.audit import logger as audit
from eden.control.models.audit import AuditAction
from eden.control.models.tenant import (
    Consultancy,
    SchemaStatus,
    SubscriptionTier,
    Tenant,
    TenantSchema,
    TenantStatus,
)
from eden.db.session import control_session
from eden.dependencies import control_db
from eden.provisioning import provision_tenant
from eden.security.principal import AuthContext
from eden.security.scopes import RequiresScope

router = APIRouter(prefix="/control/tenants", tags=["control-plane"])


class TenantCreate(BaseModel):
    consultancy_id: uuid.UUID
    slug: str = Field(..., pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    legal_name: str = Field(..., min_length=2, max_length=256)
    subscription_tier: SubscriptionTier = SubscriptionTier.trial
    feature_flags: dict = Field(default_factory=dict)
    custom_domain: str | None = None
    retention_policy: dict = Field(default_factory=dict)
    dpdp_data_fiduciary_contact: str | None = None


class TenantOut(BaseModel):
    id: uuid.UUID
    slug: str
    status: TenantStatus
    schema_name: str
    schema_status: SchemaStatus


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: TenantCreate,
    auth: AuthContext = Depends(RequiresScope("tenants:provision")),
    session: AsyncSession = Depends(control_db),
) -> TenantOut:
    consultancy = (
        await session.execute(
            select(Consultancy).where(Consultancy.id == body.consultancy_id)
        )
    ).scalar_one_or_none()
    if consultancy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "consultancy not found")

    tenant = Tenant(
        consultancy_id=body.consultancy_id,
        slug=body.slug,
        legal_name=body.legal_name,
        status=TenantStatus.pending,
        subscription_tier=body.subscription_tier,
        feature_flags=body.feature_flags,
        custom_domain=body.custom_domain,
        retention_policy=body.retention_policy,
        dpdp_data_fiduciary_contact=body.dpdp_data_fiduciary_contact,
    )
    session.add(tenant)
    await session.flush()

    await audit.record(
        session,
        auth=auth,
        action=AuditAction.WRITE,
        resource_type="tenant",
        resource_id=str(tenant.id),
        delta={"after": {"slug": tenant.slug, "tier": tenant.subscription_tier.value}},
    )
    # Commit the tenant row before DDL (provisioning uses its own engine/txns).
    await session.commit()

    schema_name = await provision_tenant(str(tenant.id))

    async with control_session() as s2:
        tenant = (
            await s2.execute(select(Tenant).where(Tenant.id == tenant.id))
        ).scalar_one()
        tenant.status = TenantStatus.active
        ts = (
            await s2.execute(
                select(TenantSchema).where(TenantSchema.tenant_id == tenant.id)
            )
        ).scalar_one()
        await audit.record(
            s2,
            auth=auth,
            action=AuditAction.WRITE,
            resource_type="tenant_schema",
            resource_id=schema_name,
            delta={"after": {"status": ts.status.value}},
        )
        return TenantOut(
            id=tenant.id,
            slug=tenant.slug,
            status=tenant.status,
            schema_name=ts.schema_name,
            schema_status=ts.status,
        )
