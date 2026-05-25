# EDEN

> *"Your one-stop garden for everything HR."*

A multi-party HR-services SaaS: a consultancy operates it, client companies
consume it, and external referral partners feed talent acquisition into it.

The full architecture — multi-tenancy model, 5-party authorization, bitemporal
employment data, hash-chained audit, partner bridge, build phases — is in
[`docs/EDEN_ARCHITECTURE.md`](docs/EDEN_ARCHITECTURE.md).

## Repository layout

```
docs/
  EDEN_ARCHITECTURE.md   Locked architecture spec (v0.3)
  SALVAGE.md             Map of what was ported from the prototype + what
                         was left in git history for later slices
eden/                    The product. FastAPI + Postgres (schema-per-tenant).
  src/eden/              Application code
  migrations/            Alembic for control plane; SQL templates for tenants
  tests/                 Pytest suite
```

## Status

P0 scaffold landed (control plane, tenant provisioning, partner referral
state machine). The first product slice in flight is **Recruitment / ATS** —
delivered as an API on the new architecture.

## History

This repo previously hosted a single-tenant browser+Flask prototype
("talenttrack"). It was removed at the v0.1.0 cleanup; see `docs/SALVAGE.md`
for what was salvaged and how to retrieve anything else from git history.

## Knowledge graph (local tooling, optional)

A [graphify](https://github.com/safishamsi/graphify) knowledge graph of this
repo can be built locally — Claude Code consults it before grepping files, so
queries about the codebase are cheaper and more accurate. Outputs live in
`graphify-out/` (gitignored).

Run `/graphify --update` after meaningful changes:

- **Code-only changes** → free (AST re-runs, no LLM tokens).
- **Doc changes** (`docs/EDEN_ARCHITECTURE.md`, this README, `CHANGELOG.md`,
  `docs/SALVAGE.md`, `eden/README.md`, `eden/docker-compose.yml`) → costs
  tokens (LLM semantic re-extraction).

If `graphify-out/` doesn't exist, run `/graphify .` once to build it.
