"""Principals: any actor that can authenticate (consultancy member, client
user, partner, auditor). Identity itself is owned by Keycloak; this row is
the local projection keyed by the Keycloak subject (`sub`)."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from eden.db.base import ControlBase
from eden.db.mixins import AuditMixin


class PartyKind(str, enum.Enum):
    consultancy = "consultancy"
    client = "client"
    partner = "partner"
    auditor = "auditor"


class Principal(ControlBase, AuditMixin):
    __tablename__ = "principals"
    __table_args__ = (
        UniqueConstraint("keycloak_sub", name="uq_principals_keycloak_sub"),
        Index("ix_principals_home_party", "home_party", "home_party_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keycloak_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    home_party: Mapped[PartyKind] = mapped_column(
        Enum(PartyKind, name="party_kind", inherit_schema=True), nullable=False
    )
    # consultancy_id / tenant_id / partner_id depending on home_party.
    home_party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
