import sqlite3
from pathlib import Path

db_files = [
    Path("database/ayra_chat.db"),
    Path("database/ayra_memory.db"),
    Path("database/memory.db")
]

for db in db_files:
    print("=" * 60)
    print(f"DATABASE: {db}")
    if not db.exists():
        print("DOES NOT EXIST")
        continue
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    for name, sql in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{name}"')
        count = cur.fetchone()[0]
        print(f"\n--- TABLE: {name} (count={count}) ---")
        print(f"SCHEMA: {sql}")
        cur.execute(f'PRAGMA table_info("{name}")')
        columns = cur.fetchall()
        print("COLUMNS:", [col[1] for col in columns])
        cur.execute(f'SELECT * FROM "{name}" LIMIT 3')
        samples = cur.fetchall()
        print("SAMPLE ROWS:")
        for s in samples:
            print("  ", s)
    conn.close()
