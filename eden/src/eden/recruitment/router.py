"""Partner candidate ingestion endpoints.

Every endpoint is gated by `RequiresScope` (Keycloak RBAC + PDP), drives the
explicit state machine, and writes a tamper-evident audit entry inside the
same transaction as the state change.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eden.audit import logger as audit
from eden.control.models.audit import AuditAction
from eden.dependencies import tenant_db
from eden.recruitment.state_machine import IllegalTransition, apply_transition
from eden.security.principal import AuthContext
from eden.security.scopes import RequiresScope
from eden.tenant.models.recruitment import (
    Candidate,
    CandidateReferral,
    CandidateSource,
    ReferralState,
)

router = APIRouter(prefix="/recruitment", tags=["recruitment"])


class ReferralCreate(BaseModel):
    vacancy_id: uuid.UUID | None = None
    raw_candidate: dict = Field(..., description="partner-supplied candidate payload")


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class ReferralOut(BaseModel):
    id: uuid.UUID
    state: ReferralState
    candidate_id: uuid.UUID | None


async def _load(session: AsyncSession, referral_id: uuid.UUID) -> CandidateReferral:
    referral = (
        await session.execute(
            select(CandidateReferral).where(CandidateReferral.id == referral_id)
        )
    ).scalar_one_or_none()
    if referral is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral not found")
    return referral


async def _advance(
    session: AsyncSession,
    referral: CandidateReferral,
    event: str,
    auth: AuthContext,
) -> None:
    try:
        referral.state = apply_transition(referral.state, event)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    referral.updated_by = uuid.uuid5(uuid.NAMESPACE_URL, auth.keycloak_sub)
    await audit.record(
        session,
        auth=auth,
        action=AuditAction.WRITE,
        resource_type="candidate_referral",
        resource_id=str(referral.id),
        delta={"event": event, "after": {"state": referral.state.value}},
    )


@router.post("/referrals", response_model=ReferralOut, status_code=201)
async def create_referral(
    body: ReferralCreate,
    auth: AuthContext = Depends(RequiresScope("referrals:create")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = CandidateReferral(
        partner_id=uuid.uuid5(uuid.NAMESPACE_URL, auth.keycloak_sub),
        vacancy_id=body.vacancy_id,
        state=ReferralState.DRAFT,
        raw_candidate=body.raw_candidate,
    )
    session.add(referral)
    await session.flush()
    await audit.record(
        session,
        auth=auth,
        action=AuditAction.WRITE,
        resource_type="candidate_referral",
        resource_id=str(referral.id),
        delta={"event": "create", "after": {"state": referral.state.value}},
    )
    return ReferralOut(id=referral.id, state=referral.state, candidate_id=None)


@router.post("/referrals/{rid}/submit", response_model=ReferralOut)
async def submit_referral(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("referrals:create")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid)
    await _advance(session, referral, "submit", auth)
    return ReferralOut(id=referral.id, state=referral.state, candidate_id=referral.candidate_id)


@router.post("/referrals/{rid}/review", response_model=ReferralOut)
async def pick_up_for_review(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("candidates:review")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid)
    referral.reviewed_by = uuid.uuid5(uuid.NAMESPACE_URL, auth.keycloak_sub)
    await _advance(session, referral, "pick_up", auth)
    return ReferralOut(id=referral.id, state=referral.state, candidate_id=referral.candidate_id)


@router.post("/referrals/{rid}/approve", response_model=ReferralOut)
async def approve_referral(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("candidates:review")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid)
    await _advance(session, referral, "approve", auth)

    # The candidate enters the pipeline ONLY now (locked decision #6).
    payload = referral.raw_candidate
    candidate = Candidate(
        full_name=str(payload.get("full_name", "")).strip() or "UNKNOWN",
        email=payload.get("email"),
        source=CandidateSource.partner_referral,
        sourced_referral_id=referral.id,
    )
    session.add(candidate)
    await session.flush()
    referral.candidate_id = candidate.id
    return ReferralOut(id=referral.id, state=referral.state, candidate_id=candidate.id)


@router.post("/referrals/{rid}/reject", response_model=ReferralOut)
async def reject_referral(
    rid: uuid.UUID,
    body: RejectBody,
    auth: AuthContext = Depends(RequiresScope("candidates:review")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid)
    referral.reject_reason = body.reason
    await _advance(session, referral, "reject", auth)
    return ReferralOut(id=referral.id, state=referral.state, candidate_id=referral.candidate_id)
