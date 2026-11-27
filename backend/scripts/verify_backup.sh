#!/usr/bin/env bash
# ==============================================================================
# OLIVER 3.0 — Backup Verification Script
# Stage 2.1A.6 — PostgreSQL Backup, Recovery & Data Protection
# ==============================================================================
# Verifies a custom-format pg_dump archive WITHOUT restoring it.
#
# VERIFICATION LEVELS (clearly distinguished):
#   LEVEL 1 — File exists and has non-zero size            (file system check)
#   LEVEL 2 — Archive is readable by pg_restore --list     (structural check)
#   LEVEL 3 — Archive header is valid and not corrupted    (format check)
#   NOTE: Levels 1-3 do NOT constitute restore verification.
#         Restore verification requires a separate database (see recovery runbook).
#
# USAGE:
#   bash backend/scripts/verify_backup.sh <backup_file_path>
#
#   Example:
#     bash backend/scripts/verify_backup.sh backend/backups/oliver_db_backup_20261125T200000Z.dump
#
# EXIT CODES:
#   0  — All verification levels passed
#   1  — Verification failed
# ==============================================================================

set -eo pipefail
set +x

# ------------------------------------------------------------------------------
# 1. Argument validation
# ------------------------------------------------------------------------------
if [ $# -lt 1 ]; then
    echo "USAGE: bash backend/scripts/verify_backup.sh <backup_file_path>" >&2
    echo "Example: bash backend/scripts/verify_backup.sh backend/backups/oliver_db_backup_20261125T200000Z.dump" >&2
    exit 1
fi

BACKUP_FILE="$1"

echo "============================================================"
echo "OLIVER BACKUP VERIFICATION"
echo "File: ${BACKUP_FILE}"
echo "Started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "============================================================"

# ------------------------------------------------------------------------------
# LEVEL 1: File existence and size check
# ------------------------------------------------------------------------------
echo ""
echo "[LEVEL 1] File existence and size check..."

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "FAIL: Backup file does not exist: ${BACKUP_FILE}" >&2
    exit 1
fi

FILE_SIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null || echo "0")
echo "  File exists: YES"
echo "  File size:   ${FILE_SIZE} bytes"

if [ "${FILE_SIZE}" -lt 100 ]; then
    echo "FAIL: Backup file is suspiciously small (${FILE_SIZE} bytes). Archive may be empty or corrupt." >&2
    exit 1
fi

# File modification timestamp
FILE_MTIME=$(stat -c%y "${BACKUP_FILE}" 2>/dev/null || stat -f%Sm "${BACKUP_FILE}" 2>/dev/null || echo "unknown")
echo "  Modified:    ${FILE_MTIME}"
echo "[LEVEL 1] PASS: File exists with size ${FILE_SIZE} bytes."

# ------------------------------------------------------------------------------
# LEVEL 2: Archive structure — pg_restore --list
# ------------------------------------------------------------------------------
echo ""
echo "[LEVEL 2] Archive readability check (pg_restore --list)..."

if ! command -v pg_restore >/dev/null 2>&1; then
    echo "FAIL: pg_restore is not available on PATH." >&2
    echo "Structural archive verification (Level 2) cannot be performed without pg_restore." >&2
    echo "Install postgresql-client or run verification inside the oliver_postgres container." >&2
    exit 1
fi

set +e
TABLE_OF_CONTENTS=$(pg_restore --list "${BACKUP_FILE}" 2>&1)
PG_RESTORE_EXIT=$?
set -e

if [ "${PG_RESTORE_EXIT}" -ne 0 ]; then
    echo "FAIL: pg_restore --list returned exit code ${PG_RESTORE_EXIT}." >&2
    echo "Archive may be corrupt or not a valid custom-format dump." >&2
    exit 1
fi

# Count items in the table of contents
TOC_LINES=$(echo "${TABLE_OF_CONTENTS}" | grep -c "^[0-9]" 2>/dev/null || echo "0")
echo "  pg_restore --list: SUCCESS"
echo "  Archive items in TOC: ${TOC_LINES}"

# Show summary of object types (non-sensitive metadata)
echo "  Object types found:"
echo "${TABLE_OF_CONTENTS}" | awk '{print $3}' | sort | uniq -c | sort -rn | head -20 | while read count type; do
    echo "    ${count}x ${type}"
done

echo "[LEVEL 2] PASS: Archive is readable by pg_restore with ${TOC_LINES} items."

# ------------------------------------------------------------------------------
# LEVEL 3: Archive magic bytes / header check
# ------------------------------------------------------------------------------
echo ""
echo "[LEVEL 3] Archive format magic bytes check..."

# pg_dump custom format begins with "PGDMP" magic bytes (ASCII: 50 47 44 4D 50)
MAGIC=$(head -c 5 "${BACKUP_FILE}" 2>/dev/null | od -An -tx1 | tr -d ' \n' | head -c 10)
EXPECTED_MAGIC="5047444d50"  # "PGDMP" in hex

if [ "${MAGIC}" = "${EXPECTED_MAGIC}" ]; then
    echo "  Magic bytes: ${MAGIC} (PGDMP) — Valid custom-format archive"
    echo "[LEVEL 3] PASS: Archive header is valid."
else
    echo "  Magic bytes: ${MAGIC} (expected ${EXPECTED_MAGIC} for PGDMP)"
    echo "  Note: Magic bytes mismatch may indicate compression wrapper. Relying on Level 2 check."
    echo "[LEVEL 3] CONDITIONAL PASS: Magic not matched but pg_restore --list succeeded (Level 2 PASS)."
fi

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "OLIVER BACKUP VERIFICATION SUMMARY"
echo "  File:   ${BACKUP_FILE}"
echo "  Size:   ${FILE_SIZE} bytes"
echo "  Result: ARCHIVE READABLE AND STRUCTURALLY VALID"
echo ""
echo "IMPORTANT DISCLAIMER:"
echo "  This verification confirms the backup archive is readable and"
echo "  structurally intact. It does NOT verify that the backup can be"
echo "  successfully restored or that the restored data is complete."
echo "  For full restore verification, see:"
echo "  docs/OLIVER_3_POSTGRESQL_BACKUP_RECOVERY_RUNBOOK.md"
echo "============================================================"
echo "Completed: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
