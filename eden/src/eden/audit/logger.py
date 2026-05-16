"""Tamper-evident audit writer (spec #2).

Each record's `row_hash` = SHA-256 over the canonical payload **plus the
previous record's hash**. Mutating or deleting any historical row changes
its hash and breaks every subsequent link, which `verify_chain` detects.
Writes are serialized per process via an asyncio lock so concomitant
requests cannot interleave and fork the chain.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eden.control.models.audit import AuditAction, AuditLog
from eden.security.principal import AuthContext

_GENESIS = "0" * 64
_chain_lock = asyncio.Lock()


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, payload: dict) -> str:
    return hashlib.sha256(f"{prev_hash}:{_canonical(payload)}".encode()).hexdigest()


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
    async with _chain_lock:
        prev_hash = (
            await session.execute(
                select(AuditLog.row_hash).order_by(AuditLog.seq.desc()).limit(1)
            )
        ).scalar_one_or_none() or _GENESIS

        entry_id = uuid.uuid4()
        occurred_at = datetime.now()
        payload = {
            "id": str(entry_id),
            "occurred_at": occurred_at.isoformat(),
            "actor_keycloak_sub": auth.keycloak_sub if auth else None,
            "tenant_id": str(auth.tenant_id) if auth else None,
            "source_ip": auth.source_ip if auth else None,
            "request_id": auth.request_id if auth else None,
            "action": action.value,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "outcome": outcome,
            "delta": delta,
        }
        row_hash = compute_hash(prev_hash, payload)

        entry = AuditLog(
            id=entry_id,
            occurred_at=occurred_at,
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
    rows = (await session.execute(select(AuditLog).order_by(AuditLog.seq.asc()))).scalars()
    for row in rows:
        payload = {
            "id": str(row.id),
            "occurred_at": row.occurred_at.isoformat(),
            "actor_keycloak_sub": row.actor_keycloak_sub,
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
            "source_ip": row.source_ip,
            "request_id": row.request_id,
            "action": row.action.value,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "outcome": row.outcome,
            "delta": row.delta,
        }
        if row.prev_hash != prev or row.row_hash != compute_hash(prev, payload):
            return False, row.seq
        prev = row.row_hash
    return True, None
