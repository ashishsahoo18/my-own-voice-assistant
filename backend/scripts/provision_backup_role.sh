#!/usr/bin/env bash
# ==============================================================================
# OLIVER 3.0 — Backup Role Provisioning Script
# Stage 2.1A.6 — PostgreSQL Backup, Recovery & Data Protection
# ==============================================================================
# Creates and configures the dedicated oliver_backup_user role with the
# minimum privileges necessary for pg_dump logical backup of oliver_db.
#
# PRIVILEGE RATIONALE:
#   pg_dump --format=custom performs a logical backup by executing SELECT on
#   every table, reading sequences, and reading schema metadata. It does NOT
#   require superuser, REPLICATION, pg_read_all_data, or physical file access.
#   Required grants:
#     - CONNECT on oliver_db
#     - USAGE on schema public
#     - SELECT on all existing tables in public schema
#     - SELECT/USAGE on all existing sequences in public schema
#     - SELECT on information_schema and pg_catalog (implicit for any login role)
#   Future tables: handled via ALTER DEFAULT PRIVILEGES on oliver_migrator.
#
# SAFETY:
#   - set +x prevents password exposure in shell traces.
#   - Passwords are never echoed, printed, or interpolated into SQL literals
#     directly; they are passed through psql -v and %L quoting.
#   - Script is idempotent: safe to run on an already-provisioned cluster.
#   - Does NOT modify oliver_db schema, data, or existing role permissions.
#   - CONNECTION LIMIT 1: backup jobs are sequential; cap prevents runaway.
#
# USAGE (run from project root with docker exec or psql available):
#   POSTGRES_ADMIN_USER=postgres \
#   POSTGRES_BACKUP_PASSWORD=<secure_password_min_16_chars> \
#   docker exec -i oliver_postgres bash < backend/scripts/provision_backup_role.sh
#
# Or from inside the container after copying the script.
# ==============================================================================

set -eo pipefail
set +x  # Strictly prevent secret exposure in shell traces

# ------------------------------------------------------------------------------
# 1. Required environment variable validation
# ------------------------------------------------------------------------------
for var in POSTGRES_BACKUP_PASSWORD; do
    val="${!var}"
    if [ -z "$val" ]; then
        echo "FATAL PROVISION ERROR: Required environment variable $var is unset or empty." >&2
        exit 1
    fi
    if [ "${#val}" -lt 16 ]; then
        echo "FATAL PROVISION ERROR: $var must be at least 16 characters for security." >&2
        exit 1
    fi
done

POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-postgres}"

echo "OLIVER 3.0: Provisioning oliver_backup_user with least-privilege backup grants..."

# ------------------------------------------------------------------------------
# 2. Create the backup role (idempotent)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_ADMIN_USER" \
     --dbname "postgres" \
     -v backup_pw="$POSTGRES_BACKUP_PASSWORD" <<- 'EOSQL'
    -- Create backup role with strict least-privilege constraints
    SELECT format(
        'CREATE ROLE oliver_backup_user WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1;',
        :'backup_pw'
    )
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oliver_backup_user') \gexec
EOSQL

echo "OLIVER 3.0: oliver_backup_user role created (or already exists)."

# ------------------------------------------------------------------------------
# 3. Grant CONNECT on oliver_db to backup role (SEC-01 compliance)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_ADMIN_USER" \
     --dbname "postgres" <<- 'EOSQL'
    -- Allow backup role to connect to the application database only
    GRANT CONNECT ON DATABASE oliver_db TO oliver_backup_user;
    -- Explicitly deny connection to test database (defense in depth)
    REVOKE CONNECT ON DATABASE oliver_test FROM oliver_backup_user;
EOSQL

echo "OLIVER 3.0: CONNECT granted on oliver_db; revoked from oliver_test."

# ------------------------------------------------------------------------------
# 4. Grant schema USAGE and read access on oliver_db
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_ADMIN_USER" \
     --dbname "oliver_db" <<- 'EOSQL'
    -- Schema visibility (required for pg_dump to enumerate objects)
    GRANT USAGE ON SCHEMA public TO oliver_backup_user;

    -- Read access on all current tables in public schema
    -- (pg_dump uses SELECT to export table data)
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO oliver_backup_user;

    -- Read access on all current sequences (required for sequence state export)
    GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO oliver_backup_user;

    -- Configure default privileges so future tables/sequences created by
    -- oliver_migrator (during Alembic migrations) are automatically accessible
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT SELECT ON TABLES TO oliver_backup_user;
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT SELECT, USAGE ON SEQUENCES TO oliver_backup_user;
EOSQL

echo "OLIVER 3.0: SELECT privileges and default privileges configured for oliver_backup_user."

# ------------------------------------------------------------------------------
# 5. Verify provisioned role attributes (non-sensitive output only)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_ADMIN_USER" \
     --dbname "postgres" <<- 'EOSQL'
    SELECT
        rolname,
        rolsuper,
        rolcreaterole,
        rolcreatedb,
        rolreplication,
        rolbypassrls,
        rolconnlimit,
        rolcanlogin
    FROM pg_roles
    WHERE rolname = 'oliver_backup_user';
EOSQL

echo "OLIVER 3.0: Backup role provisioning completed successfully."
