"""Liveness / readiness. Public (whitelisted in the tenant router) so probes
do not need a token."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from eden import __version__
from eden.db.session import engine

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "alive", "version": __version__}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "db": f"unreachable: {exc}"}
    return {"status": "ready"}


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
