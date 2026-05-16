"""Centralized, tamper-evident audit log (spec #2; schema: eden_control).

Every row links to the previous one by SHA-256 hash chain
(`prev_hash` -> `row_hash`). Altering or deleting any historical row breaks
the chain for all later rows, which the verifier detects. The table is
append-only by convention; a DB trigger blocking UPDATE/DELETE is added in
the migration for true WORM behaviour.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import BigInteger, DateTime, Enum, Identity, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from eden.db.base import ControlBase
from eden.db.mixins import utcnow


class AuditAction(str, enum.Enum):
    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"


class AuditLog(ControlBase):
    """No AuditMixin here: the audit log IS the audit record and is immutable."""

    __tablename__ = "audit_logs"

    # Monotonic sequence: defines chain order independent of wall-clock skew.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )
    occurred_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Actor & context.
    actor_principal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_keycloak_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # What happened.
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success", nullable=False)

    # JSON delta of the change: {"before": {...}, "after": {...}}.
    delta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Tamper-evidence chain.
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
