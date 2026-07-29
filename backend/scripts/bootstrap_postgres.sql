\set ON_ERROR_STOP on

\connect template1
CREATE EXTENSION IF NOT EXISTS vector;

\connect agent_platform

SELECT 'CREATE ROLE agent_migrator LOGIN NOSUPERUSER CREATEDB NOCREATEROLE PASSWORD ''changeme_in_production'''
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'agent_migrator'
)
\gexec

SELECT 'CREATE ROLE agent_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD ''changeme_in_production'''
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'agent_app'
)
\gexec

SELECT 'CREATE ROLE agent_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS PASSWORD ''changeme_in_production'''
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'agent_backup'
)
\gexec

SELECT 'CREATE ROLE agent_restore LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD ''changeme_in_production'''
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = 'agent_restore'
)
\gexec

ALTER ROLE agent_migrator LOGIN NOSUPERUSER CREATEDB NOCREATEROLE;
ALTER ROLE agent_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE agent_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;
ALTER ROLE agent_restore LOGIN NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

ALTER DATABASE agent_platform OWNER TO agent_migrator;

SELECT 'CREATE DATABASE agent_platform OWNER agent_app'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'agent_platform'
)
\gexec

SELECT 'CREATE DATABASE agent_platform_test OWNER agent_migrator'
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_database
    WHERE datname = 'agent_platform_test'
)
\gexec

REVOKE ALL ON DATABASE agent_platform FROM PUBLIC;
REVOKE ALL ON DATABASE agent_platform_test FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE agent_platform TO agent_app, agent_migrator;
GRANT CONNECT, TEMPORARY ON DATABASE agent_platform_test TO agent_app, agent_migrator;
GRANT CONNECT, TEMPORARY ON DATABASE agent_platform TO agent_backup;
GRANT USAGE ON SCHEMA public TO agent_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_backup;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agent_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE agent_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO agent_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE agent_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO agent_backup;

\echo PostgreSQL project databases are ready.
