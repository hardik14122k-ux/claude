-- =============================================================================
-- Tenant schema template — migration 0001
--
-- Applied by eden.provisioning.schema_provisioner INSIDE the target
-- client_<uuid> schema (search_path is already set to it). Idempotent so a
-- failed tenant can be retried. Enum types are created in the tenant schema,
-- so each tenant is fully self-contained.
--
-- Every table carries the mandatory audit metadata (spec #2). Bi-temporal
-- tables additionally carry effective-dating columns + a partial unique
-- index enforcing a single current version (spec #1).
-- =============================================================================

-- --- enums -------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE referral_state AS ENUM
        ('Draft','Partner_Submitted','Consultancy_Reviewing','Approved','Rejected');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE candidate_source AS ENUM ('direct','partner_referral');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- --- candidates --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name           varchar(256)     NOT NULL,
    email               varchar(320),
    source              candidate_source NOT NULL DEFAULT 'direct',
    sourced_referral_id uuid,
    -- mandatory audit metadata (spec #2)
    created_at          timestamptz      NOT NULL DEFAULT now(),
    updated_at          timestamptz      NOT NULL DEFAULT now(),
    created_by          uuid,
    updated_by          uuid,
    version_id          integer          NOT NULL DEFAULT 1
);

-- --- candidate_referrals (consultancy review queue / state machine) ----------
CREATE TABLE IF NOT EXISTS candidate_referrals (
    id            uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id    uuid           NOT NULL,
    vacancy_id    uuid,
    state         referral_state NOT NULL DEFAULT 'Draft',
    raw_candidate jsonb          NOT NULL,
    candidate_id  uuid           REFERENCES candidates(id),
    reviewed_by   uuid,
    reject_reason text,
    created_at    timestamptz    NOT NULL DEFAULT now(),
    updated_at    timestamptz    NOT NULL DEFAULT now(),
    created_by    uuid,
    updated_by    uuid,
    version_id    integer        NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_candidate_referrals_partner ON candidate_referrals (partner_id);
CREATE INDEX IF NOT EXISTS ix_candidate_referrals_state   ON candidate_referrals (state);

-- --- payroll_bands (bi-temporal, spec #1) ------------------------------------
CREATE TABLE IF NOT EXISTS payroll_bands (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_entity_id uuid        NOT NULL,
    code            varchar(32) NOT NULL,
    currency        varchar(3)  NOT NULL DEFAULT 'INR',
    min_ctc         numeric(14,2) NOT NULL,
    max_ctc         numeric(14,2) NOT NULL,
    -- effective dating
    effective_key   uuid        NOT NULL,
    valid_from      timestamptz NOT NULL DEFAULT now(),
    valid_to        timestamptz,
    is_current      boolean     NOT NULL DEFAULT true,
    -- audit metadata
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid,
    updated_by      uuid,
    version_id      integer     NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_payroll_bands_effective_key ON payroll_bands (effective_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payroll_bands_current
    ON payroll_bands (effective_key) WHERE is_current;

-- --- employment_terms (bi-temporal, spec #1) ---------------------------------
CREATE TABLE IF NOT EXISTS employment_terms (
    id              uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     uuid         NOT NULL,
    legal_entity_id uuid         NOT NULL,
    designation     varchar(128) NOT NULL,
    employment_type varchar(32)  NOT NULL,
    payroll_band_id uuid         NOT NULL REFERENCES payroll_bands(id),
    effective_key   uuid         NOT NULL,
    valid_from      timestamptz  NOT NULL DEFAULT now(),
    valid_to        timestamptz,
    is_current      boolean      NOT NULL DEFAULT true,
    created_at      timestamptz  NOT NULL DEFAULT now(),
    updated_at      timestamptz  NOT NULL DEFAULT now(),
    created_by      uuid,
    updated_by      uuid,
    version_id      integer      NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_employment_terms_effective_key ON employment_terms (effective_key);
CREATE UNIQUE INDEX IF NOT EXISTS uq_employment_terms_current
    ON employment_terms (effective_key) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_employment_terms_employee ON employment_terms (employee_id);
