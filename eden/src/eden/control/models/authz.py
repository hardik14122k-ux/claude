"""Authorization model consumed by the in-process PDP (locked decision #7).

Keycloak issues coarse roles/scopes in the token; this table set carries the
fine-grained, scoped, time-bound permission model the PDP evaluates. The
`PolicyDecisionPoint` interface keeps an OPA/Cedar swap-in possible later
without touching call sites.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from eden.db.base import ControlBase
from eden.db.mixins import AuditMixin


class Effect(str, enum.Enum):
    allow = "allow"
    deny = "deny"


class ScopeType(str, enum.Enum):
    platform = "platform"
    consultancy = "consultancy"
    client = "client"
    legal_entity = "legal_entity"
    department = "department"
    team = "team"
    self_ = "self"
    referred = "referred"


class Permission(ControlBase, AuditMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), primary_key=True)  # 'candidates:review'
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    min_clearance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(default=False, nullable=False)


class Role(ControlBase, AuditMixin):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # platform|consultancy|client|partner
    is_system: Mapped[bool] = mapped_column(default=True, nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id"), nullable=True
    )  # null = system role


class RolePermission(ControlBase, AuditMixin):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True
    )
    effect: Mapped[Effect] = mapped_column(
        Enum(Effect, name="authz_effect", inherit_schema=True), default=Effect.allow, nullable=False
    )


class RoleAssignment(ControlBase, AuditMixin):
    """The heart of the model: principal → role, scoped and time-bound."""

    __tablename__ = "role_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)

    scope_type: Mapped[ScopeType] = mapped_column(
        Enum(ScopeType, name="authz_scope_type", inherit_schema=True), nullable=False
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    module_mask: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    clearance_ceiling: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    record_scope: Mapped[str] = mapped_column(String(16), default="all", nullable=False)

    valid_from: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
