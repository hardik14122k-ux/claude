"""Per-tenant recruitment template (resolved via search_path).

Spec #4: partner candidate ingestion is an explicit state machine
(Draft -> Partner_Submitted -> Consultancy_Reviewing -> Approved/Rejected),
not a boolean. The candidate row is only created when a referral is
Approved, so an unvetted referral never appears in the client pipeline
(consultancy review queue — locked decision #6).
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from eden.db.base import TenantBase
from eden.db.mixins import AuditMixin


class ReferralState(str, enum.Enum):
    DRAFT = "Draft"
    PARTNER_SUBMITTED = "Partner_Submitted"
    CONSULTANCY_REVIEWING = "Consultancy_Reviewing"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class CandidateSource(str, enum.Enum):
    direct = "direct"
    partner_referral = "partner_referral"


class CandidateReferral(TenantBase, AuditMixin):
    """The consultancy review queue. `raw_candidate` holds the partner-supplied
    payload until a recruiter approves; `candidate_id` is linked only on
    approval."""

    __tablename__ = "candidate_referrals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    vacancy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    state: Mapped[ReferralState] = mapped_column(
        # values_callable: persist the enum VALUES ('Draft', …) — the SQL
        # template defines the pg type with values, while SQLAlchemy's
        # default would send member NAMES ('DRAFT') and fail at runtime.
        Enum(
            ReferralState,
            name="referral_state",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ReferralState.DRAFT,
        nullable=False,
    )
    raw_candidate: Mapped[dict] = mapped_column(JSONB, nullable=False)

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Candidate(TenantBase, AuditMixin):
    """Created only when a referral is Approved, or directly by recruiters."""

    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    source: Mapped[CandidateSource] = mapped_column(
        Enum(CandidateSource, name="candidate_source"),
        default=CandidateSource.direct,
        nullable=False,
    )
    sourced_referral_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
