-- Give the application role a login for local development.

\set ON_ERROR_STOP on

ALTER ROLE charie_app WITH LOGIN PASSWORD :'app_password';

-- Read back what the role can actually do.
SELECT rolname,
       rolsuper      AS is_superuser,
       rolbypassrls  AS can_bypass_rls,
       rolcreatedb   AS can_create_db,
       rolcreaterole AS can_create_role
FROM pg_roles
WHERE rolname = 'charie_app';
