-- Locked decision #10: the application uses ONE pooled, low-privilege role.
-- It must NOT own schemas and must NOT have CREATE on the database — only
-- eden_owner (used by Alembic + the provisioner) performs DDL.

CREATE ROLE eden_app LOGIN PASSWORD 'eden_app_pw';

REVOKE CREATE ON DATABASE eden FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- eden_app gets USAGE/DML on schemas at provision time (granted by the
-- provisioner per client schema). Nothing is granted globally here.
GRANT CONNECT ON DATABASE eden TO eden_app;
