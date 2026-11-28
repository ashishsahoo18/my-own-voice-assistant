# OLIVER 3.0 — Stage 2.1A.6 Final Read-Only Backup & Recovery Security Audit Report

**Audit Type:** STRICTLY READ-ONLY SECURITY AUDIT  
**Stage:** Phase 2.1 → Stage 2.1A.6 — PostgreSQL Backup, Recovery & Data Protection  
**Date:** 2026-11-25  
**Branch:** `main`  
**HEAD Commit:** `c6e8d58` (`Stage 2.1A.5: PostgreSQL connectivity implementation and audit reports`)  
**Verdict:** **CONDITIONAL PASS**

---

## 1. Final Verdict

### **CONDITIONAL PASS**

All Stage 2.1A.6 deliverables conform to OLIVER 3.0's least-privilege security architecture, credential-protection rules, atomic backup design, and isolated recovery requirements. No credentials are exposed, no existing SQLite or PostgreSQL data was modified, and no unrelated files were touched.

**Why CONDITIONAL PASS (not full PASS):**
1. **Runtime checks pending:** Docker Desktop's Linux engine daemon was offline during both implementation and audit sessions, so live execution of `provision_backup_role.sh`, `backup_postgres.sh`, and `verify_backup.sh` against the running `oliver_postgres` container remains pending.
2. **Minor hardening items identified (non-blocking):** Detailed in Section 10 below (most notably, `verify_backup.sh` exiting `0` with `ARCHIVE READABLE AND STRUCTURALLY VALID` when `pg_restore` is absent from PATH and Level 2 is skipped).

---

## 2. Exact Files Reviewed

| File | Method | Status |
|:---|:---|:---:|
| `backend/scripts/provision_backup_role.sh` | Full read (135 lines) | ✅ INSPECTED |
| `backend/scripts/backup_postgres.sh` | Full read (165 lines) | ✅ INSPECTED |
| `backend/scripts/verify_backup.sh` | Full read (148 lines) | ✅ INSPECTED |
| `backend/backups/.gitkeep` | Full read (4 lines) | ✅ INSPECTED |
| `backend/.env.example` | Full read + `git diff` | ✅ INSPECTED |
| `docs/OLIVER_3_POSTGRESQL_BACKUP_RECOVERY_RUNBOOK.md` | Full read (170 lines) | ✅ INSPECTED |
| `docs/OLIVER_3_PHASE_2_1A6_POSTGRESQL_BACKUP_RECOVERY_IMPLEMENTATION_REPORT.md` | Full read (223 lines) | ✅ INSPECTED |
| `backend/scripts/init_postgres.sh` | Full read (111 lines) | ✅ INSPECTED |
| `backend/docker-compose.yml` | Full read (37 lines) | ✅ INSPECTED |
| `.gitignore` | Full read (43 lines) + `git check-ignore` | ✅ INSPECTED |
| `database/oliver.db` & `backend/oliver_dev.db` | Metadata check (`Get-Item`) | ✅ INSPECTED |

---

## 3. Backup Role Security Findings (`provision_backup_role.sh`)

| Check | Implementation | Assessment |
|:---|:---|:---:|
| Not a superuser | `NOSUPERUSER` explicitly set (line 68) | ✅ PASS |
| No `CREATEDB` / `CREATEROLE` | `NOCREATEDB NOCREATEROLE` explicitly set (line 68) | ✅ PASS |
| No `REPLICATION` / `BYPASSRLS` | `NOREPLICATION NOBYPASSRLS` explicitly set (line 68) | ✅ PASS |
| Connection limit | `CONNECTION LIMIT 1` (line 68) — appropriate for sequential backups | ✅ PASS |
| `CONNECT` restriction | `GRANT CONNECT ON DATABASE oliver_db` + `REVOKE CONNECT ON DATABASE oliver_test` (lines 83–85) | ✅ PASS |
| Schema visibility | `GRANT USAGE ON SCHEMA public TO oliver_backup_user` (line 97) | ✅ PASS |
| Table `SELECT` privileges | `GRANT SELECT ON ALL TABLES IN SCHEMA public` (line 101) — sufficient for `pg_dump` | ✅ PASS |
| Sequence permissions | `GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public` (line 104) | ✅ PASS (see minor note §10) |
| Default privileges (`oliver_migrator`) | `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public GRANT SELECT ON TABLES` and `GRANT SELECT, USAGE ON SEQUENCES` (lines 108–111) | ✅ PASS |
| `PUBLIC` privileges | No `PUBLIC` grants added; `init_postgres.sh` `REVOKE ALL` intact | ✅ PASS |
| Existing roles preserved | `oliver_migrator`, `oliver_app_user`, and `oliver_test_user` untouched | ✅ PASS |

**Finding:** `provision_backup_role.sh` uses idempotent `SELECT format(... %L ...) WHERE NOT EXISTS ... \gexec` with `psql -v` parameterization, matching the audited DEF-01 pattern from Stage 2.1A.2.

---

## 4. Backup Implementation Findings (`backup_postgres.sh`)

| Check | Implementation | Assessment |
|:---|:---|:---:|
| `pg_dump` targeting | `--host=${PG_HOST} --port=${PG_PORT} --username=oliver_backup_user --dbname=oliver_db` (lines 110–114) | ✅ PASS |
| Archive format & compression | `--format=custom --compress=9` (lines 115–116) | ✅ PASS |
| Atomic temporary file | Writes to `${BACKUP_TMP_PATH}` (`*.dump.tmp`), renames to `${BACKUP_PATH}` only after validation (lines 55, 118, 148) | ✅ PASS |
| Timestamp collision prevention | UTC timestamp `YYYYMMDDTHHMMSSZ` + explicit `[ -f "${BACKUP_PATH}" ]` guard exiting `1` (lines 52, 94–98) | ✅ PASS |
| Exit-code handling | `set +e`, captures `DUMP_EXIT_CODE=$?`, deletes `.tmp` and exits `1` on non-zero (lines 109–133) | ✅ PASS |
| Minimum size validation | Checks `BACKUP_SIZE -lt 100`, removes `.tmp` and exits `2` (lines 140–145) | ✅ PASS |
| Partial backups isolated | `.tmp` file never renamed on failure; cannot be mistaken for completed `.dump` | ✅ PASS |
| Disk-space / permission failures | `pg_dump` non-zero exit or `mv` failure under `set -eo pipefail` fails cleanly | ✅ PASS (see `trap` note §10) |
| No auto-deletion | Old backups are never automatically deleted | ✅ PASS |

---

## 5. Credential Handling Findings

| Check | Assessment |
|:---|:---:|
| Shell tracing disabled | `set +x` present in `provision_backup_role.sh` (line 38), `backup_postgres.sh` (line 42), `verify_backup.sh` (line 27) | ✅ PASS |
| Minimum password length enforced | Enforced `>= 16` chars in both `provision_backup_role.sh` and `backup_postgres.sh` | ✅ PASS |
| No hardcoded passwords | Zero passwords in scripts, `.env.example`, or docs | ✅ PASS |
| `PGPASSWORD` scoping | Exported only immediately before `pg_dump` (line 107), `--no-password` passed (line 117), immediately `unset PGPASSWORD` (line 123) | ✅ PASS |
| Error messages | Unset/short password errors never echo the variable value | ✅ PASS |
| `.env` protection | `backend/.env` remains Git-ignored (`.gitignore:2:.env`) | ✅ PASS |

---

## 6. Archive Verification Findings (`verify_backup.sh`)

| Level | Implemented Check | Assessment |
|:---|:---|:---:|
| Level 1 | File existence (`-f`), size (`>= 100` bytes), modification timestamp (lines 52–69) | ✅ PASS |
| Level 2 | `pg_restore --list "${BACKUP_FILE}"` TOC readability + object-type count summary (lines 81–103) | ✅ PASS (see §10 if `pg_restore` missing) |
| Level 3 | First 5 bytes magic-byte check against `5047444d50` (`PGDMP`) (lines 113–129) | ✅ PASS |
| Restore disclaimer | Explicitly states Levels 1–3 do NOT verify successful restoration (lines 12–13, 141–146) | ✅ PASS |

---

## 7. Recovery Safety Findings (`OLIVER_3_POSTGRESQL_BACKUP_RECOVERY_RUNBOOK.md`)

| Check | Assessment |
|:---|:---:|
| Separate temporary database used | `oliver_restore_verify` (Section 4, Steps 3–6) | ✅ PASS |
| `oliver_db` never dropped/overwritten | Explicit `CAUTION` banner + read-only baseline check on `oliver_db` in Step 1 | ✅ PASS |
| PostgreSQL volume preserved | `oliver_postgres_data` never overwritten or deleted | ✅ PASS |
| Prerequisites documented | PostgreSQL `16.8`, `oliver_migrator`, `oliver_backup_user`, `oliver_postgres` health | ✅ PASS |
| Ownership & privileges considered | `--no-owner --role=oliver_migrator`; cutover notes re-applying `oliver_app_user` & `oliver_backup_user` grants | ✅ PASS |
| Failed restoration handling | Captures stderr, drops only `oliver_restore_verify`, verifies `oliver_db` intact, tests prior archive | ✅ PASS |
| Safe cleanup | Restricted to `DROP DATABASE IF EXISTS oliver_restore_verify;` after verification | ✅ PASS |
| Retention policy documented | Minimum 7 daily backups + pre-migration snapshots; no auto-deletion | ✅ PASS |

---

## 8. Git Status & Preservation Evidence

`git status --short` verified at audit time:
```text
 M backend/.env.example
?? backend/scripts/backup_postgres.sh
?? backend/scripts/provision_backup_role.sh
?? backend/scripts/verify_backup.sh
?? docs/OLIVER_3_PHASE_2_1A6_POSTGRESQL_BACKUP_RECOVERY_IMPLEMENTATION_REPORT.md
?? docs/OLIVER_3_POSTGRESQL_BACKUP_RECOVERY_RUNBOOK.md
```

- **Git ignore verification:** `git check-ignore -v backend/backups/test.dump` → `.gitignore:29:backups/	backend/backups/test.dump` ✅
- **No unrelated modifications:** Only `backend/.env.example` modified (+5/-1 lines, placeholders only) ✅
- **No credentials staged or committed:** Confirmed ✅
- **SQLite databases untouched:**
  - `database/oliver.db`: `192,512` bytes, `07-11-2026 19:38:26` ✅
  - `backend/oliver_dev.db`: `94,208` bytes, `07-11-2026 18:12:44` ✅
- **PostgreSQL schema / Alembic:** No Alembic commands executed; no application tables created ✅

---

## 9. Runtime Checks Still Pending

Because Docker Desktop was offline during this stage:
1. Live execution of `backend/scripts/provision_backup_role.sh` against `oliver_postgres`.
2. Live verification of `oliver_backup_user` authentication, `pg_roles` flags, and denied DDL/write/cross-DB access.
3. Live execution of `backend/scripts/backup_postgres.sh` (or `docker exec` `pg_dump`) against `oliver_db` and repeated-run collision check.
4. Live execution of `pg_restore --list` on a real `.dump` file generated from `oliver_db`.
5. Live verification that `oliver_app_user`, `oliver_migrator`, and `oliver_test_user` privileges remain unchanged.

---

## 10. Blockers & Recommended Corrections

| ID | Severity | Finding | Recommended Action |
|:---|:---:|:---|:---|
| **BLK-01** | Blocker (Environmental) | Docker Desktop is offline; live PostgreSQL backup/role checks cannot run yet | Start Docker Desktop, run `provision_backup_role.sh` and a live backup/verify cycle before Stage 2.1A.7 |
| **AUD-01** | Minor | In `verify_backup.sh` (lines 77–80, 139), if `pg_restore` is missing from PATH, Level 2 is skipped yet the script still exits `0` and prints `ARCHIVE READABLE AND STRUCTURALLY VALID` | Fail (or exit non-zero) if `pg_restore` is unavailable, or report `PARTIAL (Level 2 skipped)` |
| **AUD-02** | Low / Hardening | `provision_backup_role.sh` grants `SELECT, USAGE` on sequences (lines 104, 111); `pg_dump` only requires `SELECT` on sequences | Optionally narrow to `GRANT SELECT ON ALL SEQUENCES` / `GRANT SELECT ON SEQUENCES` |
| **AUD-03** | Low / Hardening | `backup_postgres.sh` cleans `*.tmp` on non-zero exit, but has no `trap` for `SIGINT`/`SIGTERM` cleanup | Optionally add `trap 'rm -f "${BACKUP_TMP_PATH}"; unset PGPASSWORD' INT TERM` |
| **AUD-04** | Informational | Runbook Section 4 does not explicitly mention checking free disk space before `pg_restore` | Optionally add a disk-space check before Step 4 |
