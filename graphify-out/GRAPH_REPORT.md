# Graph Report - .  (2026-05-25)

## Corpus Check
- Corpus is ~15,838 words - fits in a single context window. You may not need a graph.

## Summary
- 372 nodes · 743 edges · 35 communities (28 shown, 7 thin omitted)
- Extraction: 64% EXTRACTED · 36% INFERRED · 0% AMBIGUOUS · INFERRED: 268 edges (avg confidence: 0.55)
- Token cost: 56,741 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Architecture Spec & Principals|Architecture Spec & Principals]]
- [[_COMMUNITY_DB Sessions & Search Path|DB Sessions & Search Path]]
- [[_COMMUNITY_Tenant Onboarding API|Tenant Onboarding API]]
- [[_COMMUNITY_Recruitment Router & Models|Recruitment Router & Models]]
- [[_COMMUNITY_Control-Plane ORM Models|Control-Plane ORM Models]]
- [[_COMMUNITY_Bitemporal & Audit Mixins|Bitemporal & Audit Mixins]]
- [[_COMMUNITY_CV Parser|CV Parser]]
- [[_COMMUNITY_Hash-Chain Audit Logger|Hash-Chain Audit Logger]]
- [[_COMMUNITY_Policy Decision Point|Policy Decision Point]]
- [[_COMMUNITY_Referral State Machine|Referral State Machine]]
- [[_COMMUNITY_Keycloak Auth & Principal|Keycloak Auth & Principal]]
- [[_COMMUNITY_Cleanup & Salvage History|Cleanup & Salvage History]]
- [[_COMMUNITY_App Entrypoint & Health|App Entrypoint & Health]]
- [[_COMMUNITY_JDCV Matcher|JD/CV Matcher]]
- [[_COMMUNITY_Alembic Control Migrations|Alembic Control Migrations]]
- [[_COMMUNITY_Matcher Tests|Matcher Tests]]
- [[_COMMUNITY_CV Parser Tests|CV Parser Tests]]
- [[_COMMUNITY_Control Models Package|Control Models Package]]
- [[_COMMUNITY_EDEN Package Root|EDEN Package Root]]
- [[_COMMUNITY_Tenant Models Package|Tenant Models Package]]
- [[_COMMUNITY_Test Bootstrap|Test Bootstrap]]
- [[_COMMUNITY_Schema Naming Helper|Schema Naming Helper]]

## God Nodes (most connected - your core abstractions)
1. `AuditMixin` - 24 edges
2. `AuditAction` - 22 edges
3. `ControlBase` - 22 edges
4. `TenantSchema` - 19 edges
5. `SchemaStatus` - 18 edges
6. `BitemporalMixin` - 18 edges
7. `RequiresScope` - 18 edges
8. `ReferralState` - 17 edges
9. `Tenant` - 17 edges
10. `TenantStatus` - 16 edges

## Surprising Connections (you probably didn't know these)
- `P0 scaffold status (Recruitment/ATS slice)` --references--> `Build phases P0-P5`  [INFERRED]
  README.md → docs/EDEN_ARCHITECTURE.md
- `talenttrack prototype history` --references--> `v0.1.0 cleanup release`  [INFERRED]
  README.md → CHANGELOG.md
- `bool` --uses--> `ReferralState`  [INFERRED]
  eden/src/eden/recruitment/state_machine.py → eden/src/eden/tenant/models/recruitment.py
- `bool` --uses--> `ControlBase`  [INFERRED]
  eden/migrations/env.py → eden/src/eden/db/base.py
- `EDEN (one-stop HR garden)` --references--> `P0 Locked Decisions (§0.1)`  [EXTRACTED]
  README.md → docs/EDEN_ARCHITECTURE.md

## Hyperedges (group relationships)
- **Five-party RBAC model participants** — eden_architecture_consultancy_owner, eden_architecture_consultancy_member, eden_architecture_client_owner, eden_architecture_client_member, eden_architecture_recruitment_partner [EXTRACTED 1.00]
- **Schema-per-tenant isolation mechanism** — eden_architecture_schema_per_client, eden_architecture_eden_control_schema, eden_architecture_tenant_router, eden_architecture_schema_provisioner, eden_architecture_intra_schema_rls [EXTRACTED 0.95]
- **Defense-in-depth authorization stack** — eden_architecture_pdp, eden_architecture_schema_per_client, eden_architecture_intra_schema_rls, eden_architecture_field_masking [EXTRACTED 1.00]

## Communities (35 total, 7 thin omitted)

### Community 0 - "Architecture Spec & Principals"
Cohesion: 0.06
Nodes (48): Periodic access recertification campaigns, Auditor / Compliance principal, Break-glass session (time-boxed emergency access), Build phases P0-P5, Clearance tiers L0-L4 (data sensitivity), Client Member (HR/Manager/Employee) principal, Client Owner principal, Consultancy Member principal (+40 more)

### Community 1 - "DB Sessions & Search Path"
Cohesion: 0.08
Nodes (31): BaseSettings, assert_valid_tenant_schema(), control_session(), Engines and request-scoped sessions.  Locked decision #10: the application conne, Unit-of-work session pinned to the shared control plane (no tenant data)., Unit-of-work session scoped to one client schema.      Order matters: the tenant, tenant_session(), control_schema() (+23 more)

### Community 2 - "Tenant Onboarding API"
Cohesion: 0.17
Nodes (30): create_tenant(), Control-plane tenant onboarding (P0 exit criteria #2).  Creating a tenant regist, TenantCreate, TenantOut, BaseHTTPMiddleware, AsyncSession, AuthContext, int (+22 more)

### Community 3 - "Recruitment Router & Models"
Cohesion: 0.25
Nodes (29): BaseModel, CandidateReferral, Per-client tenant template. No schema qualifier — the tenant router     selects, TenantBase, AsyncSession, AuthContext, str, UUID (+21 more)

### Community 4 - "Control-Plane ORM Models"
Cohesion: 0.14
Nodes (22): ControlBase, Declarative base. Control-plane models bind to the `eden_control` schema; tenant, Shared control plane. All tables live in schema `eden_control`., AuditMixin, Mandatory metadata on every persisted row (spec #2)., DeclarativeBase, Effect, Permission (+14 more)

### Community 5 - "Bitemporal & Audit Mixins"
Cohesion: 0.13
Nodes (20): Effective-dating helper (spec #1).  `supersede()` is the ONLY supported way to c, Close `current` and return a new in-effect version with `changes` applied., supersede(), BitemporalMixin, __mapper_args__(), Cross-cutting column mixins.  Spec #2: EVERY table carries created_by / updated_, Effective-dated row (spec #1). Rows are immutable in time:      * ``effective_ke, utcnow() (+12 more)

### Community 6 - "CV Parser"
Cohesion: 0.24
Nodes (20): BinaryIO, bytes, int, str, _decode_best(), _estimate_years(), _extract_docx(), _extract_education() (+12 more)

### Community 7 - "Hash-Chain Audit Logger"
Cohesion: 0.21
Nodes (18): _canonical(), compute_hash(), Tamper-evident audit writer (spec #2).  Each record's `row_hash` = SHA-256 over, Append one tamper-evident entry. Must run inside the caller's txn so     the aud, Recompute the whole chain. Returns (ok, first_broken_seq)., record(), verify_chain(), AuditAction (+10 more)

### Community 8 - "Policy Decision Point"
Cohesion: 0.18
Nodes (15): str, AuthContext, Request, str, AccessRequest, allow(), Decision, deny() (+7 more)

### Community 9 - "Referral State Machine"
Cohesion: 0.20
Nodes (16): bool, str, apply_transition(), is_terminal(), permission_for(), Explicit referral state machine (spec #4).  Draft -> Partner_Submitted -> Consul, Return the next state, or raise IllegalTransition. Pure function —     persisten, resolve() (+8 more)

### Community 10 - "Keycloak Auth & Principal"
Cohesion: 0.18
Nodes (14): str, Request, str, _extract_roles(), Keycloak token verification (locked decision #8).  Cryptographic verification on, Verify signature + claims and return the trusted token contents.      Raises Tok, TokenClaims, verify_token() (+6 more)

### Community 11 - "Cleanup & Salvage History"
Cohesion: 0.19
Nodes (14): Ported cv_parser.py into eden, Ported matcher.py into eden, Pre-cleanup commit 8c51c3e, Removed talenttrack frontend/server/supabase, v0.1.0 cleanup release, Gap analysis vs prototype, Repository layout (docs/, eden/), talenttrack prototype history (+6 more)

### Community 12 - "App Entrypoint & Health"
Cohesion: 0.21
Nodes (9): healthz(), livez(), Liveness / readiness. Public (whitelisted in the tenant router) so probes do not, readyz(), create_app(), EDEN P0 application entrypoint.  Wires: tenant routing middleware (the fail-safe, str, FastAPI (+1 more)

### Community 13 - "JD/CV Matcher"
Cohesion: 0.27
Nodes (11): int, str, _normalize_skills(), rank_candidate_against_all(), rank_candidates_against_vacancy(), JD ↔ CV matcher.  Given a candidate (parsed CV fields + raw CV text) and a vacan, Return vacancies annotated with match scores, highest total first., Return candidates annotated with match scores for a single vacancy. (+3 more)

### Community 14 - "Alembic Control Migrations"
Cohesion: 0.29
Nodes (3): bool, _include_object(), Alembic environment for the eden_control schema ONLY.  Per-client tenant schemas

## Knowledge Gaps
- **24 isolated node(s):** `Request`, `BinaryIO`, `int`, `int`, `str` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `RequiresScope` connect `Recruitment Router & Models` to `Policy Decision Point`, `Tenant Onboarding API`, `App Entrypoint & Health`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Why does `AuditMixin` connect `Control-Plane ORM Models` to `Tenant Onboarding API`, `Recruitment Router & Models`, `Bitemporal & Audit Mixins`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Why does `AuditAction` connect `Hash-Chain Audit Logger` to `Tenant Onboarding API`, `Recruitment Router & Models`, `Control-Plane ORM Models`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `AuditMixin` (e.g. with `EmploymentTerm` and `PayrollBand`) actually correct?**
  _`AuditMixin` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `AuditAction` (e.g. with `str` and `AsyncSession`) actually correct?**
  _`AuditAction` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `ControlBase` (e.g. with `Principal` and `Consultancy`) actually correct?**
  _`ControlBase` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `TenantSchema` (e.g. with `ControlBase` and `AuditMixin`) actually correct?**
  _`TenantSchema` has 17 INFERRED edges - model-reasoned connections that need verification._