"""Control-plane tenancy graph (schema: eden_control).

Spec #3: the `tenants` table carries subscription tier, feature flags,
custom domain mappings, data-retention policy and DPDP compliance markers.
`tenant_configurations` is bi-temporal (spec #1) — config changes create
time-bound versions, never overwrite.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eden.db.base import ControlBase
from eden.db.mixins import AuditMixin, BitemporalMixin


class SubscriptionTier(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    growth = "growth"
    enterprise = "enterprise"


class TenantStatus(str, enum.Enum):
    pending = "pending"  # created, schema not yet provisioned
    active = "active"
    suspended = "suspended"
    offboarding = "offboarding"
    offboarded = "offboarded"


class SchemaStatus(str, enum.Enum):
    pending = "pending"
    provisioning = "provisioning"
    ready = "ready"
    failed = "failed"
    suspended = "suspended"
    offboarded = "offboarded"


class Consultancy(ControlBase, AuditMixin):
    """The operator. One row today; multi-row when white-label is enabled."""

    __tablename__ = "consultancies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    legal_name: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Tenant(ControlBase, AuditMixin):
    """A client company. Each tenant owns exactly one client_<uuid> schema."""

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        Index("ix_tenants_custom_domain", "custom_domain"),
        Index("ix_tenants_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consultancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("consultancies.id"), nullable=False
    )

    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"), default=TenantStatus.pending, nullable=False
    )

    # --- Subscription ------------------------------------------------------
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier, name="subscription_tier"),
        default=SubscriptionTier.trial,
        nullable=False,
    )
    seat_limit: Mapped[int] = mapped_column(default=10, nullable=False)

    # --- Feature flags (per-tenant capability gating) ----------------------
    feature_flags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # --- Custom domain mapping (white-label / vanity host) -----------------
    custom_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    custom_domain_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- DPDP compliance markers (locked decision #9: India-only) ----------
    data_region: Mapped[str] = mapped_column(String(32), default="ap-south-1", nullable=False)
    dpdp_consent_artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    dpdp_data_fiduciary_contact: Mapped[str | None] = mapped_column(String(256), nullable=True)
    pii_processing_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Data-retention policy --------------------------------------------
    # e.g. {"candidates_days": 730, "payslips_years": 8, "audit_years": 8}
    retention_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    schema: Mapped["TenantSchema"] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )


class TenantSchema(ControlBase, AuditMixin):
    """Provisioning bookkeeping for a tenant's dedicated Postgres schema."""

    __tablename__ = "tenant_schemas"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), primary_key=True
    )
    schema_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    status: Mapped[SchemaStatus] = mapped_column(
        Enum(SchemaStatus, name="schema_status"), default=SchemaStatus.pending, nullable=False
    )
    provisioned_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="schema")
    versions: Mapped[list["TenantSchemaVersion"]] = relationship(
        back_populates="tenant_schema", cascade="all, delete-orphan"
    )


class TenantSchemaVersion(ControlBase, AuditMixin):
    """Which versioned tenant-template migrations have been applied per schema,
    so a failed tenant is retried, not silently skipped."""

    __tablename__ = "tenant_schema_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "migration_id", name="uq_tenant_schema_versions_tenant_id_migration"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenant_schemas.tenant_id"), nullable=False
    )
    migration_id: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant_schema: Mapped[TenantSchema] = relationship(back_populates="versions")


class TenantConfiguration(ControlBase, AuditMixin, BitemporalMixin):
    """Effective-dated tenant settings (spec #1). Changing a key closes the
    current version and inserts a new one; history is fully reconstructable."""

    __tablename__ = "tenant_configurations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    config_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
