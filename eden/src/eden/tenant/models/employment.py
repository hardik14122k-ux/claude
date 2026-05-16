"""Per-tenant bi-temporal HR template (spec #1).

Employment terms and payroll bands are effective-dated: a raise or band
revision closes the current version (valid_to = effective date) and inserts
a new one. The full history is reconstructable for any past date — required
for correct retro payroll and audit.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from eden.db.base import TenantBase
from eden.db.mixins import AuditMixin, BitemporalMixin


class EmploymentTerm(TenantBase, AuditMixin, BitemporalMixin):
    __tablename__ = "employment_terms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    designation: Mapped[str] = mapped_column(String(128), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payroll_band_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payroll_bands.id"), nullable=False
    )


class PayrollBand(TenantBase, AuditMixin, BitemporalMixin):
    __tablename__ = "payroll_bands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    min_ctc: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    max_ctc: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
