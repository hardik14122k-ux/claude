"""eden_control ORM models. Importing this module registers every table on
`ControlBase.metadata` (used by Alembic autogenerate)."""

from eden.control.models.audit import AuditAction, AuditLog
from eden.control.models.authz import (
    Effect,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    ScopeType,
)
from eden.control.models.principal import PartyKind, Principal
from eden.control.models.tenant import (
    Consultancy,
    SchemaStatus,
    SubscriptionTier,
    Tenant,
    TenantConfiguration,
    TenantSchema,
    TenantSchemaVersion,
    TenantStatus,
)

__all__ = [
    "AuditAction",
    "AuditLog",
    "Effect",
    "Permission",
    "Role",
    "RoleAssignment",
    "RolePermission",
    "ScopeType",
    "PartyKind",
    "Principal",
    "Consultancy",
    "SchemaStatus",
    "SubscriptionTier",
    "Tenant",
    "TenantConfiguration",
    "TenantSchema",
    "TenantSchemaVersion",
    "TenantStatus",
]
