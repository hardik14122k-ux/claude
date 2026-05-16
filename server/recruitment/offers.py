"""Offer letter generation and lifecycle.

States: draft → sent → accepted/declined/expired/revoked.
Acceptance is the trigger for onboarding.handoff_to_employee().
"""
from __future__ import annotations

from typing import Any

from .. import db as recruitment_db
from ..shared import audit, notifications
from ..shared.utils import new_id, now_iso


def list_offers(tenant_id: str, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM offers WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if status and status != "all":
        sql += " AND status = ?"; params.append(status)
    sql += " ORDER BY created_at DESC"
    with recruitment_db.connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def get(tenant_id: str, oid: str) -> dict | None:
    with recruitment_db.connect() as c:
        r = c.execute(
            "SELECT * FROM offers WHERE tenant_id = ? AND id = ?",
            (tenant_id, oid),
        ).fetchone()
    return dict(r) if r else None


def create(tenant_id: str, data: dict, *, actor_id: str | None = None) -> dict:
    oid = new_id("ofr")
    with recruitment_db.connect() as c:
        c.execute(
            """INSERT INTO offers
                (id, tenant_id, candidate_id, vacancy_id, offered_ctc, offered_position,
                 join_date, expiry_date, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (oid, tenant_id, data["candidate_id"], data.get("vacancy_id"),
             float(data["offered_ctc"]), data.get("offered_position", ""),
             data.get("join_date", ""), data.get("expiry_date", ""),
             data.get("notes", ""), now_iso()),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="create",
                  entity_type="offer", entity_id=oid,
                  message=f'Offer drafted: ₹{data["offered_ctc"]:,.0f}')
    return get(tenant_id, oid)


def send(tenant_id: str, oid: str, *, actor_id: str | None = None) -> bool:
    offer = get(tenant_id, oid)
    if not offer or offer["status"] != "draft":
        return False
    cand = recruitment_db.get_candidate(offer["candidate_id"])
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE offers SET status = 'sent', sent_at = ? WHERE id = ?",
            (now_iso(), oid),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="send",
                  entity_type="offer", entity_id=oid, message="Offer sent")
    if cand and cand.get("email"):
        notifications.notify(
            email=cand["email"], phone=cand.get("phone"),
            subject="Your offer letter",
            body=offer_letter_text(offer, cand),
        )
    return True


def decide(
    tenant_id: str, oid: str, *, accept: bool, actor_id: str | None = None,
) -> dict | None:
    offer = get(tenant_id, oid)
    if not offer or offer["status"] != "sent":
        return None
    new_status = "accepted" if accept else "declined"
    with recruitment_db.connect() as c:
        c.execute(
            "UPDATE offers SET status = ?, decided_at = ? WHERE id = ?",
            (new_status, now_iso(), oid),
        )
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action=new_status,
                  entity_type="offer", entity_id=oid,
                  message=f"Offer {new_status}")
    if accept:
        # Move candidate forward and trigger onboarding.
        recruitment_db.move_candidate(offer["candidate_id"], "hired")
    return get(tenant_id, oid)


def offer_letter_text(offer: dict, candidate: dict) -> str:
    """Render a minimal plain-text offer letter for email body / PDF source."""
    return f"""Dear {candidate.get('name', 'Candidate')},

We are pleased to extend an offer of employment for the position of
{offer.get('offered_position') or 'the role you applied for'}.

Annual CTC: ₹{offer.get('offered_ctc', 0):,.2f}
Tentative join date: {offer.get('join_date') or 'TBD'}
This offer is valid until: {offer.get('expiry_date') or 'two weeks from issuance'}

Please reply to confirm your acceptance.

Regards,
The People Team
"""
