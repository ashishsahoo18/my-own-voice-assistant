#!/usr/bin/env bash
# ==============================================================================
# OLIVER 3.0 — PostgreSQL Logical Backup Script
# Stage 2.1A.6 — PostgreSQL Backup, Recovery & Data Protection
# ==============================================================================
# Creates a compressed custom-format pg_dump backup of oliver_db using the
# dedicated oliver_backup_user role.
#
# BACKUP FORMAT:
#   pg_dump --format=custom produces a compressed, non-plain-text archive
#   that supports selective restoration, parallel restore, and integrity
#   inspection via pg_restore --list. It is the recommended format for
#   production backups when using pg_dump.
#
# SAFETY GUARANTEES:
#   - set +x prevents password exposure in shell traces.
#   - PGPASSWORD is set only in this process's environment and never printed.
#   - Backup is first written to a .tmp file; renamed to final name only on
#     successful pg_dump exit (prevents partial backups appearing complete).
#   - Script is non-destructive: performs no writes to oliver_db.
#   - Script is idempotent and timestamped; never overwrites existing backups.
#   - POSTGRES_ADMIN_USER is never used here; only oliver_backup_user.
#
# USAGE:
#   Required environment variables (read from backend/.env or shell):
#     POSTGRES_BACKUP_PASSWORD   — oliver_backup_user password (never printed)
#     POSTGRES_HOST              — PostgreSQL host (default: 127.0.0.1)
#     POSTGRES_PORT              — PostgreSQL port (default: 5432)
#     POSTGRES_BACKUP_DIR        — Backup output directory (default: ./backend/backups)
#
#   Run from project root:
#     source backend/.env   # (or export variables manually)
#     bash backend/scripts/backup_postgres.sh
#
# EXIT CODES:
#   0  — Backup completed successfully
#   1  — Configuration or pg_dump error
#   2  — Backup file not created or empty
# ==============================================================================

set -eo pipefail
set +x  # Strictly prevent password exposure in shell traces

# ------------------------------------------------------------------------------
# 1. Configuration (all configurable, all with safe defaults)
# ------------------------------------------------------------------------------
BACKUP_USER="oliver_backup_user"
BACKUP_DB="oliver_db"
PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
BACKUP_BASE_DIR="${POSTGRES_BACKUP_DIR:-./backend/backups}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILENAME="oliver_db_backup_${TIMESTAMP}.dump"
BACKUP_PATH="${BACKUP_BASE_DIR}/${BACKUP_FILENAME}"
BACKUP_TMP_PATH="${BACKUP_PATH}.tmp"

# ------------------------------------------------------------------------------
# 2. Environment validation — fail early, never expose credentials
# ------------------------------------------------------------------------------
if [ -z "${POSTGRES_BACKUP_PASSWORD:-}" ]; then
    echo "FATAL BACKUP ERROR: POSTGRES_BACKUP_PASSWORD is not set." >&2
    echo "Export POSTGRES_BACKUP_PASSWORD or source backend/.env before running." >&2
    exit 1
fi

# Validate password minimum length without printing it
if [ "${#POSTGRES_BACKUP_PASSWORD}" -lt 16 ]; then
    echo "FATAL BACKUP ERROR: POSTGRES_BACKUP_PASSWORD is too short (minimum 16 characters)." >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# 3. Prerequisite checks
# ------------------------------------------------------------------------------
if ! command -v pg_dump >/dev/null 2>&1; then
    echo "FATAL BACKUP ERROR: pg_dump is not available on PATH." >&2
    echo "Ensure postgresql-client is installed or run from inside the container." >&2
    exit 1
fi

PG_DUMP_VERSION=$(pg_dump --version 2>&1 | head -1)
echo "OLIVER BACKUP: Using ${PG_DUMP_VERSION}"
echo "OLIVER BACKUP: Target database: ${BACKUP_DB} on ${PG_HOST}:${PG_PORT}"
echo "OLIVER BACKUP: Backup role: ${BACKUP_USER}"
echo "OLIVER BACKUP: Output directory: ${BACKUP_BASE_DIR}"
echo "OLIVER BACKUP: Backup filename: ${BACKUP_FILENAME}"

# ------------------------------------------------------------------------------
# 4. Create backup output directory (safe; no-op if already exists)
# ------------------------------------------------------------------------------
mkdir -p "${BACKUP_BASE_DIR}"

# Collision guard: fail if the target filename already exists
if [ -f "${BACKUP_PATH}" ]; then
    echo "FATAL BACKUP ERROR: Target backup file already exists: ${BACKUP_PATH}" >&2
    echo "This should not occur with timestamp-based filenames. Check system clock." >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# 5. Execute pg_dump — write to .tmp first (atomic rename on success)
# ------------------------------------------------------------------------------
echo "OLIVER BACKUP: Starting pg_dump at $(date -u +"%Y-%m-%dT%H:%M:%SZ")..."

# PGPASSWORD is passed via environment only — never appears in command arguments
# pg_dumpall or streaming replication is NOT used; this is a safe logical dump
export PGPASSWORD="${POSTGRES_BACKUP_PASSWORD}"

set +e  # Capture exit code without immediate exit
pg_dump \
    --host="${PG_HOST}" \
    --port="${PG_PORT}" \
    --username="${BACKUP_USER}" \
    --dbname="${BACKUP_DB}" \
    --format=custom \
    --compress=9 \
    --no-password \
    --file="${BACKUP_TMP_PATH}"
DUMP_EXIT_CODE=$?
set -e

# Immediately unset PGPASSWORD after use — do not leave in environment
unset PGPASSWORD

# ------------------------------------------------------------------------------
# 6. Validate pg_dump result
# ------------------------------------------------------------------------------
if [ "${DUMP_EXIT_CODE}" -ne 0 ]; then
    echo "FATAL BACKUP ERROR: pg_dump exited with code ${DUMP_EXIT_CODE}." >&2
    echo "OLIVER BACKUP: Removing failed temporary backup file..." >&2
    rm -f "${BACKUP_TMP_PATH}"
    exit 1
fi

if [ ! -f "${BACKUP_TMP_PATH}" ]; then
    echo "FATAL BACKUP ERROR: pg_dump reported success but output file not found: ${BACKUP_TMP_PATH}" >&2
    exit 2
fi

BACKUP_SIZE=$(stat -c%s "${BACKUP_TMP_PATH}" 2>/dev/null || stat -f%z "${BACKUP_TMP_PATH}" 2>/dev/null || echo "0")
if [ "${BACKUP_SIZE}" -lt 100 ]; then
    echo "FATAL BACKUP ERROR: Backup file is suspiciously small (${BACKUP_SIZE} bytes). Possible empty dump." >&2
    rm -f "${BACKUP_TMP_PATH}"
    exit 2
fi

# Atomic rename: only visible as final filename after successful completion
mv "${BACKUP_TMP_PATH}" "${BACKUP_PATH}"

# ------------------------------------------------------------------------------
# 7. Report success
# ------------------------------------------------------------------------------
FINAL_SIZE=$(stat -c%s "${BACKUP_PATH}" 2>/dev/null || stat -f%z "${BACKUP_PATH}" 2>/dev/null || echo "unknown")
echo "OLIVER BACKUP: pg_dump completed successfully."
echo "OLIVER BACKUP: File: ${BACKUP_PATH}"
echo "OLIVER BACKUP: Size: ${FINAL_SIZE} bytes"
echo "OLIVER BACKUP: Timestamp: ${TIMESTAMP}"
echo "OLIVER BACKUP: Done at $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""
echo "OLIVER BACKUP: To verify this backup, run:"
echo "  bash backend/scripts/verify_backup.sh ${BACKUP_PATH}"
echo ""
echo "OLIVER BACKUP: Retention note: Old backups are NOT automatically deleted."
echo "  Review and prune backend/backups/ manually per your retention policy."
echo "  Recommendation: Keep at minimum the last 7 daily backups."
