"""Partner candidate ingestion endpoints.

Every endpoint is gated by `RequiresScope` (Keycloak RBAC + PDP), drives the
explicit state machine, and writes a tamper-evident audit entry inside the
same transaction as the state change.

Partner visibility (spec §4.4 / §8): a partner principal sees ONLY their own
referrals. Until the intra-schema RLS policies land (P1), that restriction
is enforced here at the query layer — every read path MUST filter by
`partner_id == auth.principal_id` for partner callers, and the test suite
proves it. Do not add a read path without the filter.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

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

# Coarse partner detection for P0 query-level isolation. P1 replaces this
# with record_scope from RoleAssignment / RLS session GUCs (§8).
_PARTNER_ROLE = "partner"


def _is_partner(auth: AuthContext) -> bool:
    return _PARTNER_ROLE in auth.roles


class ReferralCreate(BaseModel):
    vacancy_id: uuid.UUID | None = None
    raw_candidate: dict = Field(..., description="partner-supplied candidate payload")


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class ReferralOut(BaseModel):
    id: uuid.UUID
    state: ReferralState
    candidate_id: uuid.UUID | None
    vacancy_id: uuid.UUID | None = None
    reject_reason: str | None = None


class ReferralPage(BaseModel):
    items: list[ReferralOut]
    total: int
    limit: int
    offset: int


def _out(r: CandidateReferral) -> ReferralOut:
    return ReferralOut(
        id=r.id,
        state=r.state,
        candidate_id=r.candidate_id,
        vacancy_id=r.vacancy_id,
        reject_reason=r.reject_reason,
    )


async def _load(
    session: AsyncSession, referral_id: uuid.UUID, auth: AuthContext
) -> CandidateReferral:
    referral = (
        await session.execute(
            select(CandidateReferral).where(CandidateReferral.id == referral_id)
        )
    ).scalar_one_or_none()
    # Partners get 404 (not 403) for other partners' referrals: existence is
    # itself information they must not learn.
    if referral is None or (
        _is_partner(auth) and referral.partner_id != auth.principal_id
    ):
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
    referral.updated_by = auth.principal_id
    try:
        await audit.record(
            session,
            auth=auth,
            action=AuditAction.WRITE,
            resource_type="candidate_referral",
            resource_id=str(referral.id),
            delta={"event": event, "after": {"state": referral.state.value}},
        )
    except StaleDataError as exc:
        # Optimistic-concurrency loss (version_id raced by another writer)
        # is a client-retryable conflict, not a server error.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "referral was modified concurrently; retry"
        ) from exc


@router.post("/referrals", response_model=ReferralOut, status_code=201)
async def create_referral(
    body: ReferralCreate,
    auth: AuthContext = Depends(RequiresScope("referrals:create")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = CandidateReferral(
        partner_id=auth.principal_id,
        vacancy_id=body.vacancy_id,
        state=ReferralState.DRAFT,
        raw_candidate=body.raw_candidate,
        created_by=auth.principal_id,
        updated_by=auth.principal_id,
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
    return _out(referral)


@router.get("/referrals", response_model=ReferralPage)
async def list_referrals(
    auth: AuthContext = Depends(RequiresScope("referrals:read")),
    session: AsyncSession = Depends(tenant_db),
    state: ReferralState | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReferralPage:
    query = select(CandidateReferral)
    count = select(func.count()).select_from(CandidateReferral)
    if _is_partner(auth):
        # Query-level partner isolation (see module docstring).
        query = query.where(CandidateReferral.partner_id == auth.principal_id)
        count = count.where(CandidateReferral.partner_id == auth.principal_id)
    if state is not None:
        query = query.where(CandidateReferral.state == state)
        count = count.where(CandidateReferral.state == state)
    total = (await session.execute(count)).scalar_one()
    rows = (
        (
            await session.execute(
                query.order_by(CandidateReferral.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ReferralPage(
        items=[_out(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/referrals/{rid}", response_model=ReferralOut)
async def get_referral(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("referrals:read")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid, auth)
    return _out(referral)


@router.post("/referrals/{rid}/submit", response_model=ReferralOut)
async def submit_referral(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("referrals:create")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid, auth)
    await _advance(session, referral, "submit", auth)
    return _out(referral)


@router.post("/referrals/{rid}/review", response_model=ReferralOut)
async def pick_up_for_review(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("candidates:review")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid, auth)
    referral.reviewed_by = auth.principal_id
    await _advance(session, referral, "pick_up", auth)
    return _out(referral)


@router.post("/referrals/{rid}/approve", response_model=ReferralOut)
async def approve_referral(
    rid: uuid.UUID,
    auth: AuthContext = Depends(RequiresScope("candidates:review")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid, auth)
    await _advance(session, referral, "approve", auth)

    # The candidate enters the pipeline ONLY now (locked decision #6).
    payload = referral.raw_candidate
    candidate = Candidate(
        full_name=str(payload.get("full_name", "")).strip() or "UNKNOWN",
        email=payload.get("email"),
        source=CandidateSource.partner_referral,
        sourced_referral_id=referral.id,
        created_by=auth.principal_id,
        updated_by=auth.principal_id,
    )
    session.add(candidate)
    await session.flush()
    referral.candidate_id = candidate.id
    return _out(referral)


@router.post("/referrals/{rid}/reject", response_model=ReferralOut)
async def reject_referral(
    rid: uuid.UUID,
    body: RejectBody,
    auth: AuthContext = Depends(RequiresScope("candidates:review")),
    session: AsyncSession = Depends(tenant_db),
) -> ReferralOut:
    referral = await _load(session, rid, auth)
    referral.reject_reason = body.reason
    await _advance(session, referral, "reject", auth)
    return _out(referral)
