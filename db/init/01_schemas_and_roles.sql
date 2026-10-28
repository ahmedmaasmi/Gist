-- db/init/01_schemas_and_roles.sql

-- 1. Drop default public schema creation privileges to keep namespaces strict
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- 2. Create the 4 Information Tier schemas (PRD Section 5.2)
CREATE SCHEMA IF NOT EXISTS t0_public;
CREATE SCHEMA IF NOT EXISTS t1_session;
CREATE SCHEMA IF NOT EXISTS t2_character;
CREATE SCHEMA IF NOT EXISTS t3_canonical;

-- 3. Create the two database roles
CREATE ROLE casemind_gameplay WITH LOGIN PASSWORD 'gameplay_safe_pass';
CREATE ROLE casemind_vault WITH LOGIN PASSWORD 'vault_secret_pass';

-- 4. Grant database connection rights
GRANT CONNECT ON DATABASE casemind TO casemind_gameplay, casemind_vault;

-- 5. Configure casemind_gameplay (STRICTLY T0, T1, T2 - NO T3 ACCESS)
GRANT USAGE, CREATE ON SCHEMA t0_public, t1_session, t2_character TO casemind_gameplay;

ALTER DEFAULT PRIVILEGES IN SCHEMA t0_public, t1_session, t2_character
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO casemind_gameplay;
ALTER DEFAULT PRIVILEGES IN SCHEMA t0_public, t1_session, t2_character
    GRANT USAGE, SELECT ON SEQUENCES TO casemind_gameplay;

-- Explicitly revoke everything on t3_canonical from casemind_gameplay
REVOKE ALL ON SCHEMA t3_canonical FROM casemind_gameplay;
REVOKE ALL ON SCHEMA t3_canonical FROM PUBLIC;

-- 6. Configure casemind_vault (Full access to T0-T3 for generator & post-verdict results)
GRANT USAGE, CREATE ON SCHEMA t0_public, t1_session, t2_character, t3_canonical TO casemind_vault;

ALTER DEFAULT PRIVILEGES IN SCHEMA t0_public, t1_session, t2_character, t3_canonical
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO casemind_vault;
ALTER DEFAULT PRIVILEGES IN SCHEMA t0_public, t1_session, t2_character, t3_canonical
    GRANT USAGE, SELECT ON SEQUENCES TO casemind_vault;

-- Makesure tables created by casemind_vault in T0-T2 are still readable/writable by casemind_gameplay
ALTER DEFAULT PRIVILEGES FOR ROLE casemind_vault IN SCHEMA t0_public, t1_session, t2_character
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO casemind_gameplay;
ALTER DEFAULT PRIVILEGES FOR ROLE casemind_vault IN SCHEMA t0_public, t1_session, t2_character
    GRANT USAGE, SELECT ON SEQUENCES TO casemind_gameplay;