# EDEN — P0 service (control plane + tenant provisioning)

Greenfield FastAPI service implementing the **P0** scope from
`../docs/EDEN_ARCHITECTURE.md` (v0.3, all decisions locked). The validated
HR-domain math from the prototype is ported in later phases as pure
libraries; P0 is the control plane, tenant isolation, and the partner
ingestion state machine.

## How the requested specs map to code

| Spec | Where |
|------|-------|
| **#1 Bi-temporal / effective dating** | `db/mixins.py::BitemporalMixin`, `db/bitemporal.py::supersede`, `control/models/tenant.py::TenantConfiguration`, `tenant/models/employment.py`, partial-unique `is_current` indexes in migrations |
| **#2 Audit metadata on every table** | `db/mixins.py::AuditMixin` (created/updated by/at, `version_id`) |
| **#2 Tamper-evident `audit_logs`** | `control/models/audit.py`, `audit/logger.py` (SHA-256 hash chain + `verify_chain`), WORM trigger in `migrations/versions/0001_*` |
| **#3 Rich `tenants` table** | `control/models/tenant.py::Tenant` (subscription tier, feature flags, custom domain, retention policy, DPDP markers) |
| **#3 Per-request schema routing + hard fail-safe** | `middleware/tenant_router.py`, `db/session.py` (`SET LOCAL search_path` per txn), `dependencies.py::tenant_db` (refuses a connection without a verified tenant) |
| **#4 Explicit state machine** | `recruitment/state_machine.py` (Draft → Partner_Submitted → Consultancy_Reviewing → Approved/Rejected) |
| **#4 Keycloak RBAC in FastAPI deps** | `security/keycloak.py`, `security/scopes.py::RequiresScope`, `policy/pdp.py` (swappable PDP) |

## Locked decisions honoured

Python/FastAPI · self-hosted Keycloak (JWKS verification) · in-process PDP
behind `PolicyDecisionPoint` · schema-per-client (`eden_control` +
`client_<uuid>`) · one pooled DB role + per-request `search_path` ·
India-only region.

## Layout

```
src/eden/
  config.py            typed settings (pydantic-settings)
  main.py              FastAPI app wiring
  db/                  base, mixins (audit + bitemporal), engines/sessions
  control/models/      eden_control: tenants, principals, authz, audit, provisioning
  tenant/models/       per-client template: recruitment, employment (bitemporal)
  security/            Keycloak verify, AuthContext, RequiresScope
  middleware/          TenantRoutingMiddleware (the fail-safe)
  policy/              PolicyDecisionPoint interface + in-process engine
  provisioning/        schema provisioner + migration runner
  audit/               tamper-evident hash-chain writer + verifier
  recruitment/         state machine + endpoints
  api/                 health, control-plane tenant onboarding
migrations/            Alembic (eden_control only) + tenant_template/*.sql
```

## Run locally

```bash
cp .env.example .env                  # fill in secrets
docker compose up -d db keycloak
pip install -e ".[dev]"
alembic upgrade head                  # builds eden_control
uvicorn eden.main:app --app-dir src --reload
pytest                                # pure-logic tests run without infra
```

> Note: `eden_control` is Alembic-managed. Per-client schemas are **not** —
> they are provisioned and migrated by `eden.provisioning.schema_provisioner`
> from `migrations/tenant_template/`, tracked per-tenant in
> `tenant_schema_versions` so a failed tenant is retried, not skipped.
