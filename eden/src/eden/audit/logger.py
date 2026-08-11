"""Tamper-evident audit writer (spec #2).

Each record's `row_hash` = SHA-256 over the canonical payload **plus the
previous record's hash**. Mutating or deleting any historical row changes
its hash and breaks every subsequent link, which `verify_chain` detects.

Chain writers are serialized with a Postgres transaction-scoped advisory
lock (`pg_advisory_xact_lock`), NOT an in-process lock: the audit chain is
one chain per database, and multiple API workers/replicas write to it. The
lock is acquired inside the caller's transaction and released at commit/
rollback, so the prev-hash read and the insert are atomic cluster-wide.

Timestamps are hashed as integer microseconds since the Unix epoch (UTC).
Postgres `timestamptz` round-trips at exactly microsecond precision, so the
value hashed at write time is bit-identical to the value recomputed by
`verify_chain` from the stored row — no string-formatting drift.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from eden.control.models.audit import AuditAction, AuditLog
from eden.db.mixins import utcnow
from eden.security.principal import AuthContext

_GENESIS = "0" * 64
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# Advisory lock key for the audit chain. Two int32 args (classid, objid)
# keep us clear of other users of the 64-bit advisory-lock keyspace.
_CHAIN_LOCK = (0xED, 0x0A)


def _epoch_micros(dt: datetime) -> int:
    if dt.tzinfo is None:
        raise ValueError("audit timestamps must be timezone-aware")
    return (dt - _EPOCH) // timedelta(microseconds=1)


def _norm_ip(value: object) -> str | None:
    """INET round-trips from asyncpg as ipaddress objects (host addresses may
    gain a /32 suffix). Normalize to the bare host string so write-time and
    verify-time hashes agree."""
    if value is None:
        return None
    return str(value).split("/", 1)[0]


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256(f"{prev_hash}:{_canonical(payload)}".encode()).hexdigest()


def _payload(
    *,
    entry_id: uuid.UUID,
    occurred_at: datetime,
    actor_principal_id: uuid.UUID | None,
    actor_keycloak_sub: str | None,
    tenant_id: uuid.UUID | None,
    source_ip: object,
    request_id: str | None,
    action: AuditAction,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
    delta: dict | None,
) -> dict:
    """One payload builder used by BOTH the writer and the verifier, so the
    hashed representation cannot drift between the two."""
    return {
        "id": str(entry_id),
        "occurred_at_us": _epoch_micros(occurred_at),
        "actor_principal_id": str(actor_principal_id) if actor_principal_id else None,
        "actor_keycloak_sub": actor_keycloak_sub,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "source_ip": _norm_ip(source_ip),
        "request_id": request_id,
        "action": action.value,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome,
        "delta": delta,
    }


async def record(
    session: AsyncSession,
    *,
    auth: AuthContext | None,
    action: AuditAction,
    resource_type: str,
    resource_id: str | None = None,
    delta: dict | None = None,
    outcome: str = "success",
) -> AuditLog:
    """Append one tamper-evident entry. Must run inside the caller's txn so
    the audit row commits atomically with the change it describes."""
    # Serialize chain writers across ALL workers/replicas; released at txn end.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:c, :o)"),
        {"c": _CHAIN_LOCK[0], "o": _CHAIN_LOCK[1]},
    )
    prev_hash = (
        await session.execute(
            select(AuditLog.row_hash).order_by(AuditLog.seq.desc()).limit(1)
        )
    ).scalar_one_or_none() or _GENESIS

    entry_id = uuid.uuid4()
    occurred_at = utcnow()
    payload = _payload(
        entry_id=entry_id,
        occurred_at=occurred_at,
        actor_principal_id=auth.principal_id if auth else None,
        actor_keycloak_sub=auth.keycloak_sub if auth else None,
        tenant_id=auth.tenant_id if auth else None,
        source_ip=auth.source_ip if auth else None,
        request_id=auth.request_id if auth else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        delta=delta,
    )
    row_hash = compute_hash(prev_hash, payload)

    entry = AuditLog(
        id=entry_id,
        occurred_at=occurred_at,
        actor_principal_id=auth.principal_id if auth else None,
        actor_keycloak_sub=auth.keycloak_sub if auth else None,
        tenant_id=auth.tenant_id if auth else None,
        source_ip=auth.source_ip if auth else None,
        user_agent=None,
        request_id=auth.request_id if auth else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        delta=delta,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> tuple[bool, int | None]:
    """Recompute the whole chain. Returns (ok, first_broken_seq)."""
    prev = _GENESIS
    rows = (
        await session.stream(select(AuditLog).order_by(AuditLog.seq.asc()))
    ).scalars()
    async for row in rows:
        payload = _payload(
            entry_id=row.id,
            occurred_at=row.occurred_at,
            actor_principal_id=row.actor_principal_id,
            actor_keycloak_sub=row.actor_keycloak_sub,
            tenant_id=row.tenant_id,
            source_ip=row.source_ip,
            request_id=row.request_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            outcome=row.outcome,
            delta=row.delta,
        )
        if row.prev_hash != prev or row.row_hash != compute_hash(prev, payload):
            return False, row.seq
        prev = row.row_hash
    return True, None
