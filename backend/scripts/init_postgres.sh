#!/usr/bin/env bash
# ==============================================================================
# OLIVER 3.0 — PostgreSQL Cluster Initialization Script
# Executed by official PostgreSQL Docker container on first volume initialization.
# Conforms to Stage 2.1A.2 SEC-01 through SEC-10 security closure specifications.
# ==============================================================================

set -eo pipefail
set +x # Strictly prevent secret exposure in shell traces

# ------------------------------------------------------------------------------
# 1. Environment Variable Validation
# ------------------------------------------------------------------------------
for var in POSTGRES_MIGRATOR_PASSWORD POSTGRES_APP_PASSWORD POSTGRES_TEST_PASSWORD; do
    val="${!var}"
    if [ -z "$val" ]; then
        echo "FATAL INIT ERROR: Required environment variable $var is unset or empty." >&2
        exit 1
    fi
    if [ "${#val}" -lt 16 ]; then
        echo "FATAL INIT ERROR: $var must be at least 16 characters for security." >&2
        exit 1
    fi
done

echo "OLIVER 3.0: Initializing PostgreSQL roles and databases with strict least privilege..."

# ------------------------------------------------------------------------------
# 2. Role Creation (Idempotent, Safe Parameterization via psql variables)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v migrator_pw="$POSTGRES_MIGRATOR_PASSWORD" \
     -v app_pw="$POSTGRES_APP_PASSWORD" \
     -v test_pw="$POSTGRES_TEST_PASSWORD" <<- 'EOSQL'
    -- Migration role: owns databases and schema; executes Alembic
    SELECT format(
        'CREATE ROLE oliver_migrator WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 2;',
        :'migrator_pw'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oliver_migrator') \gexec

    -- Runtime application role: DML only on oliver_db
    SELECT format(
        'CREATE ROLE oliver_app_user WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 20;',
        :'app_pw'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oliver_app_user') \gexec

    -- Test role: DDL and DML on oliver_test only
    SELECT format(
        'CREATE ROLE oliver_test_user WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10;',
        :'test_pw'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oliver_test_user') \gexec
EOSQL

# ------------------------------------------------------------------------------
# 3. Database Creation (Idempotent)
# ------------------------------------------------------------------------------
for dbname in oliver_db oliver_test; do
    if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tc "SELECT 1 FROM pg_database WHERE datname = '$dbname'" | grep -q 1; then
        echo "Creating database: $dbname (Owner: oliver_migrator)..."
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
             -c "CREATE DATABASE $dbname WITH OWNER = oliver_migrator ENCODING = 'UTF8';"
    fi
done

# ------------------------------------------------------------------------------
# 4. Connection Isolation (SEC-01: Revoke PUBLIC CONNECT)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<- 'EOSQL'
    -- Sever default PUBLIC connection rights
    REVOKE CONNECT, TEMPORARY ON DATABASE oliver_db FROM PUBLIC;
    REVOKE CONNECT, TEMPORARY ON DATABASE oliver_test FROM PUBLIC;

    -- Grant explicitly to authorized identities
    GRANT CONNECT ON DATABASE oliver_db TO oliver_migrator, oliver_app_user;
    GRANT CONNECT ON DATABASE oliver_test TO oliver_migrator, oliver_test_user;
EOSQL

# ------------------------------------------------------------------------------
# 5. Production Database Schema & Default Privileges (oliver_db)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "oliver_db" <<- 'EOSQL'
    -- Assign public schema ownership to oliver_migrator (SEC-03)
    ALTER SCHEMA public OWNER TO oliver_migrator;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO oliver_migrator;
    GRANT USAGE ON SCHEMA public TO oliver_app_user;

    -- Configure default privileges for future objects created by oliver_migrator (SEC-02)
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO oliver_app_user;
EOSQL

# ------------------------------------------------------------------------------
# 6. Test Database Schema (oliver_test — Satisfies conftest.py:383)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "oliver_test" <<- 'EOSQL'
    -- Transfer public schema ownership to oliver_test_user
    ALTER SCHEMA public OWNER TO oliver_test_user;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO oliver_test_user;
    GRANT ALL PRIVILEGES ON SCHEMA public TO oliver_test_user;
EOSQL

echo "OLIVER 3.0: PostgreSQL provisioning completed successfully."
