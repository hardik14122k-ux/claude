# EDEN

> *"Your one-stop garden for everything HR."*

A multi-party HR-services SaaS: a consultancy operates it, client companies
consume it, and external referral partners feed talent acquisition into it.
Multi-tenant (dedicated Postgres schema per client), Keycloak-authenticated,
policy-gated, with a tamper-evident audit chain.

The full architecture — multi-tenancy model, 5-party authorization, bitemporal
employment data, hash-chained audit, partner bridge, build phases — is in
[`docs/EDEN_ARCHITECTURE.md`](docs/EDEN_ARCHITECTURE.md), with visual
companions in [`docs/diagrams/`](docs/diagrams/).

## Repository layout

```
docs/
  EDEN_ARCHITECTURE.md   Locked architecture spec (v0.3)
  diagrams/              draw.io editable-SVG architecture diagrams
  SALVAGE.md             Map of what was ported from the old prototype + what
                         stays in git history for later slices
eden/                    The product. FastAPI + Postgres (schema-per-tenant).
  src/eden/              Application code (control plane, security, recruitment)
  migrations/            Alembic (control plane) + SQL templates (tenant schemas)
  keycloak/              Realm-as-code (roles, demo users, claim mappers)
  scripts/               DB init + demo seed
  tests/                 Unit + integration (real Postgres) suites
.github/workflows/       CI: ruff, mypy (advisory), unit + integration tests
```

## Quick start (local)

```bash
cd eden
docker compose up -d --build        # Postgres + Keycloak (realm auto-imported) + API
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_demo.py
```

Then get a token and call the API (demo users all have password `demo`):

```bash
TOKEN=$(curl -s http://localhost:8080/realms/eden/protocol/openid-connect/token \
  -d client_id=eden-cli -d grant_type=password \
  -d username=partner@demo.eden -d password=demo | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s http://localhost:8000/recruitment/referrals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"raw_candidate": {"full_name": "Ada Lovelace", "email": "ada@example.com"}}'
```

Interactive API docs: http://localhost:8000/docs

| Demo user | Role | Can |
|---|---|---|
| `owner@demo.eden` | consultancy owner + platform admin | everything incl. tenant provisioning |
| `recruiter@demo.eden` | consultancy recruiter | review/approve/reject referrals |
| `partner@demo.eden`, `partner2@demo.eden` | referral partner | create + read **own** referrals only |

## Development

```bash
cd eden
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest            # unit tests always; integration tests run when a Postgres
                  # is on 127.0.0.1:5433 or local pg binaries can spawn one
ruff check src tests
```

Verify the audit chain: `python -m eden.audit.verify`

## Status

**M1 (walking skeleton) in progress.** Landed: control plane + tenant
provisioning proven against real Postgres, Keycloak realm-as-code, principal
resolution, partner referral state machine with read endpoints and
query-level partner isolation, tamper-evident audit chain (advisory-locked,
WORM-triggered, verified in CI). The Recruitment / ATS slice (vacancies,
candidates, pipeline) builds on this next — see §12 of the architecture doc.

## History

This repo previously hosted a single-tenant browser+Flask prototype
("talenttrack"), removed at the v0.1.0 cleanup. `docs/SALVAGE.md` records
what was ported (CV parser, JD↔CV matcher) and how to retrieve the rest
(payroll math, HRMS logic) from git history when their slices begin.

## Knowledge graph (local tooling, optional)

A [graphify](https://github.com/safishamsi/graphify) knowledge graph of this
repo can be built locally — Claude Code consults it before grepping files.
Outputs live in `graphify-out/`. Run `/graphify --update` after meaningful
changes: code-only changes re-index for free; doc changes cost LLM tokens.
If `graphify-out/` doesn't exist, run `/graphify .` once to build it.
