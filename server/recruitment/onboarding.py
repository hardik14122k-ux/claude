"""Onboarding handoff: candidate → employee master.

Single entry point that:
1. Reads the recruitment candidate
2. Creates an employees row (links candidate_id back)
3. Returns the new employee
"""
from __future__ import annotations

from .. import db as recruitment_db
from ..hrms import employee as employee_master
from ..shared import audit


def handoff_to_employee(
    tenant_id: str,
    candidate_id: str,
    *,
    actor_id: str | None = None,
    extra: dict | None = None,
) -> dict | None:
    cand = recruitment_db.get_candidate(candidate_id)
    if not cand:
        return None
    emp = employee_master.from_candidate(tenant_id, cand, actor_id=actor_id, extra=extra)
    with recruitment_db.connect() as c:
        audit.log(c, actor_id=actor_id, tenant_id=tenant_id, action="onboard",
                  entity_type="employee", entity_id=emp["id"],
                  message=f"Onboarded from candidate {candidate_id}")
    return emp
