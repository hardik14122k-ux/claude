"""End-to-end checks against a REAL Postgres: migrations, grants,
provisioning, the audit chain, and partner isolation on the referral reads.

These are exactly the failure modes pure-logic tests cannot see (and did
not: every bug fixed in the M1 audit would have been caught here).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

from eden.audit import logger as audit
from eden.config import get_settings
from eden.control.models.audit import AuditAction, AuditLog
from eden.control.models.tenant import Consultancy, Tenant, TenantStatus
from eden.db.session import admin_engine, control_session, tenant_session
from eden.provisioning import provision_tenant
from eden.recruitment.router import (
    ReferralCreate,
    create_referral,
    get_referral,
    list_referrals,
)
from eden.security.principal import AuthContext
from eden.tenant.models.recruitment import CandidateReferral

pytestmark = pytest.mark.usefixtures("pg_server")

_settings = get_settings()


async def _make_provisioned_tenant() -> tuple[uuid.UUID, str]:
    cid, tid = uuid.uuid4(), uuid.uuid4()
    async with control_session() as s:
        s.add(Consultancy(id=cid, code=f"c-{cid.hex[:8]}", legal_name="Test Consultancy"))
        await s.flush()
        s.add(
            Tenant(
                id=tid,
                consultancy_id=cid,
                slug=f"t-{tid.hex[:8]}",
                legal_name="Test Tenant",
                status=TenantStatus.active,
            )
        )
    schema = await provision_tenant(str(tid))
    return tid, schema


def _auth(
    principal_id: uuid.UUID,
    tenant_id: uuid.UUID,
    schema: str,
    roles: frozenset[str],
) -> AuthContext:
    return AuthContext(
        keycloak_sub=f"sub-{principal_id}",
        principal_id=principal_id,
        tenant_id=tenant_id,
        tenant_schema=schema,
        email=None,
        roles=roles,
        scopes=frozenset(),
        request_id="itest",
        source_ip="127.0.0.1",
    )


async def test_app_role_can_read_control_plane():
    """The pooled app role must be able to read eden_control (the grants the
    tenant router depends on for EVERY request)."""
    async with control_session() as s:
        count = (await s.execute(select(func.count()).select_from(Tenant))).scalar_one()
    assert count >= 0


async def test_provision_tenant_end_to_end_and_idempotent():
    tid, schema = await _make_provisioned_tenant()

    # The tenant template actually applied (multi-statement script), and the
    # app role can write/read inside the new schema.
    async with tenant_session(schema) as s:
        s.add(
            CandidateReferral(
                partner_id=uuid.uuid4(),
                raw_candidate={"full_name": "Probe"},
            )
        )
    async with tenant_session(schema) as s:
        n = (
            await s.execute(select(func.count()).select_from(CandidateReferral))
        ).scalar_one()
    assert n == 1

    # Re-provisioning is a no-op, not a failure.
    assert await provision_tenant(str(tid)) == schema


async def test_audit_chain_write_and_verify():
    async with control_session() as s:
        for i in range(3):
            await audit.record(
                s,
                auth=None,
                action=AuditAction.WRITE,
                resource_type="itest",
                resource_id=f"chain-{i}",
            )
    async with control_session() as s:
        ok, broken = await audit.verify_chain(s)
    assert ok, f"chain reported broken at seq={broken} without tampering"


async def test_worm_trigger_blocks_mutation():
    async with control_session() as s:
        entry = await audit.record(
            s, auth=None, action=AuditAction.WRITE, resource_type="itest", resource_id="worm"
        )
        seq = entry.seq
    with pytest.raises(Exception, match="append-only"):
        async with admin_engine.connect() as conn:
            await conn.execute(
                text(
                    f"UPDATE {_settings.control_schema}.audit_logs "
                    f"SET outcome = 'tampered' WHERE seq = :seq"
                ),
                {"seq": seq},
            )


async def test_audit_chain_detects_tampering():
    async with control_session() as s:
        entry = await audit.record(
            s, auth=None, action=AuditAction.WRITE, resource_type="itest", resource_id="tamper"
        )
        seq = entry.seq

    table = f"{_settings.control_schema}.audit_logs"
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER trg_audit_logs_worm"))
        try:
            await conn.execute(
                text(f"UPDATE {table} SET outcome = 'tampered' WHERE seq = :seq"),
                {"seq": seq},
            )
        finally:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER trg_audit_logs_worm"))

    async with control_session() as s:
        ok, broken = await audit.verify_chain(s)
    assert not ok
    assert broken == seq

    # Repair so later tests see a clean chain again.
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER trg_audit_logs_worm"))
        try:
            await conn.execute(
                text(f"UPDATE {table} SET outcome = 'success' WHERE seq = :seq"),
                {"seq": seq},
            )
        finally:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER trg_audit_logs_worm"))


async def test_partner_isolation_on_reads():
    """A partner sees ONLY their own referrals — list, and 404 on get — while
    a consultancy recruiter sees everything. Exercises the REAL router code."""
    tid, schema = await _make_provisioned_tenant()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    partner1 = _auth(p1, tid, schema, frozenset({"partner"}))
    partner2 = _auth(p2, tid, schema, frozenset({"partner"}))
    recruiter = _auth(uuid.uuid4(), tid, schema, frozenset({"consultancy_recruiter"}))

    async with tenant_session(schema) as s:
        r1 = await create_referral(
            ReferralCreate(raw_candidate={"full_name": "Alpha"}), auth=partner1, session=s
        )
    async with tenant_session(schema) as s:
        r2 = await create_referral(
            ReferralCreate(raw_candidate={"full_name": "Beta"}), auth=partner2, session=s
        )

    # List: each partner sees exactly their own; recruiter sees both.
    async with tenant_session(schema) as s:
        page1 = await list_referrals(auth=partner1, session=s, state=None, limit=50, offset=0)
        page2 = await list_referrals(auth=partner2, session=s, state=None, limit=50, offset=0)
        page_r = await list_referrals(auth=recruiter, session=s, state=None, limit=50, offset=0)
    assert {r.id for r in page1.items} == {r1.id}
    assert {r.id for r in page2.items} == {r2.id}
    assert {r1.id, r2.id} <= {r.id for r in page_r.items}

    # Get: another partner's referral 404s (existence must not leak).
    async with tenant_session(schema) as s:
        with pytest.raises(HTTPException) as exc:
            await get_referral(rid=r2.id, auth=partner1, session=s)
        assert exc.value.status_code == 404
        own = await get_referral(rid=r1.id, auth=partner1, session=s)
        assert own.id == r1.id
