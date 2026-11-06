import sqlite3
from pathlib import Path
import os
import json

db_paths = [
    Path("database/oliver.db"),
    Path("database/memory.db"),
    Path("database/ayra_chat.db"),
    Path("database/ayra_memory.db"),
]

print("=== CHECKING ALL PRODUCTION DATABASE FILES ===")
for p in db_paths:
    if not p.exists():
        print(f"File {p} does NOT exist.")
        continue
    stat = p.stat()
    print(f"\nDB: {p} (Size: {stat.st_size} bytes, Last Modified: {stat.st_mtime})")
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Tables in {p.name}: {tables}")
    for t in tables:
        if t.startswith("sqlite_") or "fts" in t:
            continue
        try:
            cur.execute(f'SELECT count(*) FROM "{t}"')
            cnt = cur.fetchone()[0]
            print(f"  Table '{t}': {cnt} rows")
            if cnt > 0:
                cur.execute(f'SELECT * FROM "{t}"')
                rows = cur.fetchall()
                for row in rows:
                    r_dict = dict(row)
                    print(f"    row: {r_dict}")
        except Exception as e:
            print(f"  Table '{t}' query error: {e}")
    conn.close()

