"""Cross-cutting column mixins.

Spec #2: EVERY table carries created_by / updated_by / created_at /
updated_at / version_id.

Spec #1: bi-temporal ("effective dating") tables additionally carry
valid_from / valid_to and never overwrite — an update closes the current
version (sets valid_to, is_current=False) and inserts a new time-bound row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


@declarative_mixin
class AuditMixin:
    """Mandatory metadata on every persisted row (spec #2)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=utcnow,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Optimistic-concurrency token; SQLAlchemy bumps it on every UPDATE and
    # raises StaleDataError if two writers race the same row.
    version_id: Mapped[int] = mapped_column(nullable=False, default=1)

    @declared_attr.directive
    @classmethod
    def __mapper_args__(cls) -> dict[str, object]:
        return {"version_id_col": cls.__table__.c.version_id}


@declarative_mixin
class BitemporalMixin:
    """Effective-dated row (spec #1). Rows are immutable in time:

    * ``effective_key``  groups all versions of one logical entity.
    * ``valid_from`` / ``valid_to``  the business-validity window.
    * ``is_current``  fast-path flag for "the version in effect now".

    A partial unique index ``(effective_key) WHERE is_current`` guarantees
    at most one live version; it is created in the migrations (control) and
    the tenant SQL template (tenant) rather than reflected here, so the
    constraint exists at the database layer regardless of the ORM.

    Mutate via :func:`eden.db.bitemporal.supersede` — never UPDATE in place.
    """

    effective_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, nullable=False, index=True
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
