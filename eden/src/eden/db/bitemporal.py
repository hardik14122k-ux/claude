"""Effective-dating helper (spec #1).

`supersede()` is the ONLY supported way to change a bi-temporal row: it
closes the current version (valid_to = now, is_current = False) and inserts
a new version carrying forward `effective_key`. Data is never overwritten.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TypeVar

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from eden.db.mixins import BitemporalMixin, utcnow

T = TypeVar("T", bound=BitemporalMixin)


async def supersede(
    session: AsyncSession,
    model: type[T],
    current: T,
    *,
    changes: dict[str, object],
    actor_id: uuid.UUID,
    effective_at: datetime | None = None,
) -> T:
    """Close `current` and return a new in-effect version with `changes` applied."""
    if not current.is_current:
        raise ValueError("Cannot supersede a non-current version")

    boundary = effective_at or utcnow()

    await session.execute(
        update(model)
        .where(
            model.effective_key == current.effective_key,
            model.is_current.is_(True),
        )
        .values(is_current=False, valid_to=boundary, updated_by=actor_id)
    )

    carried = {
        c.key: getattr(current, c.key)
        for c in current.__table__.columns  # type: ignore[attr-defined]
        if c.key
        not in {
            "id",
            "valid_from",
            "valid_to",
            "is_current",
            "created_at",
            "updated_at",
            "version_id",
        }
    }
    carried.update(changes)
    carried["effective_key"] = current.effective_key
    carried["valid_from"] = boundary
    carried["valid_to"] = None
    carried["is_current"] = True
    carried["created_by"] = actor_id
    carried["updated_by"] = actor_id

    new_version = model(**carried)
    session.add(new_version)
    await session.flush()
    return new_version
