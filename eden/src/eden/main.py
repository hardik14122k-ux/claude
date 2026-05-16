"""EDEN P0 application entrypoint.

Wires: tenant routing middleware (the fail-safe), control-plane tenant
onboarding, and the partner recruitment state machine. Domain HR modules
(P2+) plug in here later behind the same middleware + PDP.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from eden import __version__
from eden.api import health, tenants
from eden.config import get_settings
from eden.middleware import TenantRoutingMiddleware
from eden.recruitment import router as recruitment_router

_settings = get_settings()
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))
_log = structlog.get_logger("eden")


def create_app() -> FastAPI:
    app = FastAPI(
        title="EDEN",
        version=__version__,
        description="Multi-party HR-services SaaS — P0 control plane.",
    )

    # The fail-safe runs first: no protected request reaches a handler (or a
    # tenant DB connection) without a cryptographically verified tenant.
    app.add_middleware(TenantRoutingMiddleware)

    app.include_router(health.router)
    app.include_router(tenants.router)
    app.include_router(recruitment_router)

    @app.on_event("startup")
    async def _startup() -> None:
        _log.info(
            "eden.start",
            version=__version__,
            env=_settings.env,
            region=_settings.region,
            fail_closed=_settings.fail_closed,
        )

    return app


app = create_app()
