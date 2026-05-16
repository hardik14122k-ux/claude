"""Structured audit logging for all HRMS actions.

Every write operation should call log() so we have a complete trail:
who did what, when, to which tenant, and what changed.
"""
from __future__ import annotations

import json
import sqlite3

from .utils import now_iso


def log(
    conn: sqlite3.Connection,
    *,
    actor_id: str | None,
    tenant_id: str,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    message: str = "",
    diff: dict | None = None,
    ip: str | None = None,
) -> None:
    """Insert one structured audit entry within an existing connection/transaction."""
    conn.execute(
        """INSERT INTO audit_log
           (tenant_id, actor_id, action, entity_type, entity_id, message, diff, ip, ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tenant_id,
            actor_id or "system",
            action,
            entity_type,
            entity_id or "",
            message,
            json.dumps(diff or {}),
            ip or "",
            now_iso(),
        ),
    )


def log_activity(
    conn: sqlite3.Connection,
    type_: str,
    message: str,
    meta: dict | None = None,
) -> None:
    """Backward-compatible shim for db.log_activity calls."""
    conn.execute(
        "INSERT INTO activity (type, message, meta, ts) VALUES (?, ?, ?, ?)",
        (type_, message, json.dumps(meta or {}), now_iso()),
    )
