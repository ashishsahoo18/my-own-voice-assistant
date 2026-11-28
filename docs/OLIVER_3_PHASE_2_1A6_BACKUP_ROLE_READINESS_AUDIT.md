# OLIVER 3.0 — Stage 2.1A.6 Backup Role Readiness Audit

**Audit Type:** STRICTLY READ-ONLY ROLE READINESS AUDIT  
**Stage:** Phase 2.1 → Stage 2.1A.6 — PostgreSQL Backup, Recovery & Data Protection  
**Date:** 2026-11-25  
**Branch:** `main`  
**HEAD Commit:** `c6e8d58` (`Stage 2.1A.5: PostgreSQL connectivity implementation and audit reports`)  
**Verdict:** **READY FOR AUTHORIZED PROVISIONING (`oliver_backup_user` NOT YET PRESENT)**

---

## 1. Executive Summary

All infrastructure and credential prerequisites are verified ready:
- Docker Engine is running (`ServerVersion=29.9.3`, `OSType=linux`).
- `oliver_postgres` (`44f1d071a3d4`) is running and `(healthy)`, bound to `127.0.0.1:5432->5432/tcp`.
- Named volume `oliver_postgres_data` (`local` driver) is mounted read-write at `/var/lib/postgresql/data`.
- `POSTGRES_BACKUP_PASSWORD` is configured in `backend/.env` and meets the `>= 16` character requirement (`LEN: 21`; value not displayed).
- `oliver_db` contains `0` public tables.
- Both SQLite databases remain untouched.

**Finding:** `oliver_backup_user` **does not exist yet** in `pg_roles` (`0 rows`), and no backup-role grants or default privileges exist in `oliver_db`. Separate explicit authorization is required to execute `backend/scripts/provision_backup_role.sh`.

---

## 2. Preflight & Infrastructure Evidence

### 2.1 Docker Engine, Container & Volume

Commands executed (read-only):
```powershell
docker info --format "ServerVersion={{.ServerVersion}} OSType={{.OSType}}"
docker ps --filter "name=oliver_postgres" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
docker inspect oliver_postgres --format "{{range .Mounts}}{{.Type}}:{{.Name}}->{{.Destination}} (rw={{.RW}}); {{end}}"
docker volume ls --filter "name=oliver_postgres_data"
```

Observed output:
```text
ServerVersion=29.9.3 OSType=linux
CONTAINER ID   NAMES             STATUS                    PORTS
44f1d071a3d4   oliver_postgres   Up 11 minutes (healthy)   127.0.0.1:5432->5432/tcp
bind:->/docker-entrypoint-initdb.d/01_init_postgres.sh (rw=false); volume:oliver_postgres_data->/var/lib/postgresql/data (rw=true);
DRIVER    VOLUME NAME
local     oliver_postgres_data
```

### 2.2 Backup Credential Check (`backend/.env`)

Command executed (read-only, value never printed):
```powershell
python -c "from dotenv import dotenv_values; d=dotenv_values('backend/.env'); pw=d.get('POSTGRES_BACKUP_PASSWORD',''); print('HAS_BACKUP_PW:', bool(pw), 'LEN_OK:', len(pw)>=16, 'LEN:', len(pw))"
```

Observed output:
```text
HAS_BACKUP_PW: True LEN_OK: True LEN: 21
```

---

## 3. PostgreSQL Backup Role Inspection Evidence

### 3.1 `pg_roles` Existence & Attributes

Query:
```sql
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolconnlimit, rolcanlogin
FROM pg_roles WHERE rolname = 'oliver_backup_user';
```

Result: `(0 rows)` — `oliver_backup_user` does not exist.

### 3.2 Database `CONNECT`, Schema `USAGE`, and Default Privileges

Queries & Results:
```text
   datname   | has_connect
-------------+-------------
 oliver_db   |
 oliver_test |
(2 rows)

 schema_usage | schema_create
--------------+---------------
              |
(1 row)

 public_tables
---------------
             0
(1 row)

                         Default access privileges
      Owner      | Schema |   Type   |          Access privileges
-----------------+--------+----------+--------------------------------------
 oliver_migrator | public | sequence | oliver_app_user=rU/oliver_migrator
 oliver_migrator | public | table    | oliver_app_user=arwd/oliver_migrator
(2 rows)
```

---

## 4. Gap Comparison Against Approved Least-Privilege Design

| Requirement | Current State | Expected State (`provision_backup_role.sh`) |
|:---|:---:|:---|
| `oliver_backup_user` exists | ❌ Missing | `LOGIN`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS`, `CONNECTION LIMIT 1` |
| `CONNECT` on `oliver_db` | ❌ Missing | `GRANT CONNECT ON DATABASE oliver_db TO oliver_backup_user` |
| `CONNECT` on `oliver_test` | N/A | Explicitly revoked (`REVOKE CONNECT ON DATABASE oliver_test FROM oliver_backup_user`) |
| `USAGE` on `public` schema | ❌ Missing | `GRANT USAGE ON SCHEMA public TO oliver_backup_user` |
| `SELECT` on existing tables/sequences | ❌ Missing | `GRANT SELECT ON ALL TABLES` + `GRANT SELECT, USAGE ON ALL SEQUENCES` in `public` |
| Default privileges (`oliver_migrator`) | ❌ Missing | `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public GRANT SELECT ON TABLES` and `GRANT SELECT, USAGE ON SEQUENCES` |

---

## 5. SQLite Preservation & Git Status

- **SQLite databases untouched:**
  - `database/oliver.db`: `192,512` bytes, `07-11-2026 19:38:26`
  - `backend/oliver_dev.db`: `94,208` bytes, `07-11-2026 18:12:44`
- **`git status --short`:**
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
?? docs/OLIVER_3_PHASE_2_1A6_POSTGRESQL_BACKUP_RECOVERY_IMPLEMENTATION_REPORT.md
?? docs/OLIVER_3_POSTGRESQL_BACKUP_RECOVERY_RUNBOOK.md
```

---

## 6. Next Required Authorization

Explicit authorization is required to execute `backend/scripts/provision_backup_role.sh` against `oliver_postgres` using `POSTGRES_BACKUP_PASSWORD` from `backend/.env`, followed by live backup and `verify_backup.sh` validation.
