# OLIVER 3.0 — Stage 2.1A.6 Live Backup Runtime Validation Report

**Status:** COMPLETE & VERIFIED  
**Stage:** Phase 2.1 → Stage 2.1A.6 — Authorized Backup Role Provisioning & Live Backup Validation  
**Date:** 2026-11-25  
**Branch:** `main`  
**HEAD Commit:** `c6e8d58` (`Stage 2.1A.5: PostgreSQL connectivity implementation and audit reports`)  
**Verdict:** **PASS**

---

## 1. Executive Summary

Following explicit authorization, `oliver_backup_user` was provisioned on the live `oliver_postgres` (`postgres:16.8`) cluster using `backend/scripts/provision_backup_role.sh`, verified for least-privilege isolation, and used to execute a live logical backup of `oliver_db` via `backend/scripts/backup_postgres.sh` and 3-level archive verification via `backend/scripts/verify_backup.sh`.

All provisioning, permission, backup, verification, and preservation checks passed with zero credential exposure and zero modifications to `oliver_db` schema/data or SQLite databases.

---

## 2. Role Provisioning Result (`provision_backup_role.sh`)

- **Pre-provisioning recheck:** `SELECT count(*) FROM pg_roles WHERE rolname = 'oliver_backup_user';` → `0` (confirmed not yet present).
- **Execution:** Executed `backend/scripts/provision_backup_role.sh` inside `oliver_postgres` with `POSTGRES_BACKUP_PASSWORD` passed via container environment (`exit=0`).
- **Result:** `CREATE ROLE`, `GRANT CONNECT ON DATABASE oliver_db`, `REVOKE CONNECT ON DATABASE oliver_test`, `GRANT USAGE ON SCHEMA public`, `GRANT SELECT ON ALL TABLES/SEQUENCES`, and `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator` all succeeded.

---

## 3. Verified Role Attributes & Permissions

### 3.1 `pg_roles` Attributes

```text
rolname            | rolsuper | rolcreatedb | rolcreaterole | rolreplication | rolbypassrls | rolconnlimit | rolcanlogin
-------------------+----------+-------------+---------------+----------------+--------------+--------------+------------
oliver_backup_user | f        | f           | f             | f              | f            |            1 | t
```

### 3.2 Database, Schema, and Default Privileges

| Check | Result |
|:---|:---|
| `has_database_privilege('oliver_backup_user', 'oliver_db', 'CONNECT')` | `t` (True) |
| `has_database_privilege('oliver_backup_user', 'oliver_test', 'CONNECT')` | `f` (False) |
| `has_schema_privilege('oliver_backup_user', 'public', 'USAGE')` | `t` (True) |
| `has_schema_privilege('oliver_backup_user', 'public', 'CREATE')` | `f` (False) |
| Default privileges (`\ddp+` for `oliver_migrator`) | `oliver_backup_user=r/oliver_migrator` (tables), `oliver_backup_user=rU/oliver_migrator` (sequences); `oliver_app_user` (`arwd`, `rU`) preserved unchanged |

### 3.3 Live Authentication & Negative Isolation Tests

| Test | Exit Code | Result |
|:---|:---:|:---|
| `psql -U oliver_backup_user -d oliver_db -c "SELECT current_user, current_database();"` | `0` | Returned `oliver_backup_user \| oliver_db` |
| `psql -U oliver_backup_user -d oliver_db -c "CREATE TABLE _unauth_backup_test (id int);"` | `1` | Rejected: `ERROR: permission denied for schema public` |
| `psql -U oliver_backup_user -d oliver_test -c "SELECT 1;"` | `2` | Rejected: `FATAL: permission denied for database "oliver_test"` / `User does not have CONNECT privilege.` |

---

## 4. Live Backup Execution (`backup_postgres.sh`)

Because `pg_dump` is not installed natively on the Windows host PATH, `backend/scripts/backup_postgres.sh` was executed inside the `oliver_postgres` container (`pg_dump (PostgreSQL) 16.8 (Debian 16.8-1.pgdg120+1)`) against `127.0.0.1:5432` (`oliver_db`) as `oliver_backup_user` with `--format=custom --compress=9 --no-password`, then copied to `backend/backups/` on the host.

- **Exit Status:** `0` (`BACKUP_EXIT: 0`)
- **Archive Filename:** `oliver_db_backup_20261125T211747Z.dump`
- **Host Archive Path:** `backend/backups/oliver_db_backup_20261125T211747Z.dump`
- **Archive Size:** `2,530` bytes (valid compressed custom-format archive for empty/unmigrated `oliver_db`)
- **Credentials Exposed:** None (`PGPASSWORD` passed via process environment only and immediately `unset`).

---

## 5. Archive Verification Results (`verify_backup.sh`)

Executed `backend/scripts/verify_backup.sh` inside `oliver_postgres` against `oliver_db_backup_20261125T211747Z.dump`:

- **Exit Status:** `0` (`VERIFY_EXIT: 0`)
- **Level 1 (File existence & size):** **PASS** (`2,530` bytes, `>= 100` bytes).
- **Level 2 (`pg_restore --list`):** **PASS** (exit `0`, `4` TOC entries found for `oliver_db` / `public` schema).
- **Level 3 (Magic bytes):** **PASS** (`5047444d50 (PGDMP)` — valid custom-format archive header).
- **Summary Result:** `ARCHIVE READABLE AND STRUCTURALLY VALID` (note: restore verification into an isolated temporary DB has not been executed yet and remains a separate authorized step).

---

## 6. Database, Docker & SQLite Preservation Evidence

| Check | Result |
|:---|:---|
| `oliver_postgres` status | `Up 16 minutes (healthy)` (`127.0.0.1:5432->5432/tcp`) |
| `oliver_postgres_data` volume | Present (`local` driver) |
| `oliver_db` & `oliver_test` present | Confirmed (`oliver_db`, `oliver_test`) |
| `oliver_db` public tables | `0` (no Alembic migrations executed; no application tables created) |
| `database/oliver.db` | `192,512` bytes, `07-11-2026 19:38:26` — **UNTOUCHED** |
| `backend/oliver_dev.db` | `94,208` bytes, `07-11-2026 18:12:44` — **UNTOUCHED** |

---

## 7. Git Status

`git status --short`:
```text
 M backend/.env.example
?? backend/scripts/backup_postgres.sh
?? backend/scripts/provision_backup_role.sh
?? backend/scripts/verify_backup.sh
?? docs/OLIVER_3_PHASE_2_1A6_AUD01_CORRECTION_REPORT.md
?? docs/OLIVER_3_PHASE_2_1A6_AUD01_FINAL_VERIFICATION_AUDIT.md
?? docs/OLIVER_3_PHASE_2_1A6_AUTOMATED_BACKUP_RUNTIME_REPORT.md
?? docs/OLIVER_3_PHASE_2_1A6_BACKUP_ROLE_READINESS_AUDIT.md
?? docs/OLIVER_3_PHASE_2_1A6_FINAL_READ_ONLY_SECURITY_AUDIT_REPORT.md
?? docs/OLIVER_3_PHASE_2_1A6_LIVE_BACKUP_RUNTIME_VALIDATION_REPORT.md
?? docs/OLIVER_3_PHASE_2_1A6_POSTGRESQL_BACKUP_RECOVERY_IMPLEMENTATION_REPORT.md
?? docs/OLIVER_3_POSTGRESQL_BACKUP_RECOVERY_RUNBOOK.md
```
*(Archive `backend/backups/oliver_db_backup_20261125T211747Z.dump` is excluded by `.gitignore` `backups/`.)*

---

## 8. Warnings & Remaining Limitations

1. **Host Toolchain Note:** `pg_dump` and `pg_restore` are not installed natively on the Windows host PATH, so `backup_postgres.sh` and `verify_backup.sh` were executed inside the `oliver_postgres` container (`postgres:16.8`).
2. **Restore Verification Pending:** Archive readability (`pg_restore --list`) is verified, but isolated temporary-database restore verification (`oliver_restore_verify`) has not been executed yet and awaits separate authorization.
