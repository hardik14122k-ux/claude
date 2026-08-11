"""Seed the demo world: consultancy, tenant (provisioned), principals.

Idempotent — safe to re-run. The UUIDs are FIXED and must match
keycloak/eden-realm.json:

  tenant        11111111-1111-1111-1111-111111111111  (users' eden_tenant attr)
  consultancy   22222222-2222-2222-2222-222222222222
  principals    keycloak user ids aaaaaaaa-0000-0000-0000-00000000000{1..4}

Run (env must point at the running Postgres, e.g. the docker-compose one):

    python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from eden.control.models.principal import PartyKind, Principal
from eden.control.models.tenant import (
    Consultancy,
    Tenant,
    TenantStatus,
)
from eden.db.session import control_session
from eden.provisioning import provision_tenant

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CONSULTANCY_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

# (keycloak fixed user id, email, display name, home party)
DEMO_PRINCIPALS: list[tuple[str, str, str, PartyKind]] = [
    ("aaaaaaaa-0000-0000-0000-000000000001", "owner@demo.eden", "Olive Owner", PartyKind.consultancy),
    ("aaaaaaaa-0000-0000-0000-000000000002", "recruiter@demo.eden", "Rae Recruiter", PartyKind.consultancy),
    ("aaaaaaaa-0000-0000-0000-000000000003", "partner@demo.eden", "Pat Partner", PartyKind.partner),
    ("aaaaaaaa-0000-0000-0000-000000000004", "partner2@demo.eden", "Perry Partner-Two", PartyKind.partner),
]


async def seed() -> None:
    async with control_session() as s:
        consultancy = (
            await s.execute(select(Consultancy).where(Consultancy.id == CONSULTANCY_ID))
        ).scalar_one_or_none()
        if consultancy is None:
            s.add(
                Consultancy(
                    id=CONSULTANCY_ID, code="eden-demo", legal_name="EDEN Demo Consultancy Pvt Ltd"
                )
            )
            print("created consultancy eden-demo")

        tenant = (
            await s.execute(select(Tenant).where(Tenant.id == TENANT_ID))
        ).scalar_one_or_none()
        if tenant is None:
            s.add(
                Tenant(
                    id=TENANT_ID,
                    consultancy_id=CONSULTANCY_ID,
                    slug="acme-demo",
                    legal_name="Acme Demo Industries Pvt Ltd",
                    status=TenantStatus.pending,
                )
            )
            print("created tenant acme-demo")

    schema = await provision_tenant(str(TENANT_ID))
    print(f"tenant schema ready: {schema}")

    async with control_session() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == TENANT_ID))).scalar_one()
        if tenant.status != TenantStatus.active:
            tenant.status = TenantStatus.active
            print("tenant activated")

        for sub, email, name, party in DEMO_PRINCIPALS:
            existing = (
                await s.execute(select(Principal).where(Principal.keycloak_sub == sub))
            ).scalar_one_or_none()
            if existing is None:
                s.add(
                    Principal(
                        keycloak_sub=sub,
                        email=email,
                        display_name=name,
                        home_party=party,
                        home_party_id=(
                            CONSULTANCY_ID if party == PartyKind.consultancy else uuid.uuid5(
                                uuid.NAMESPACE_URL, f"eden-demo-partner:{email}"
                            )
                        ),
                    )
                )
                print(f"created principal {email} ({party.value})")

    print("seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
