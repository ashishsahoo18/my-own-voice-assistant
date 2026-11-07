import sqlite3, sys, os
db_path = r'C:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant\database\oliver.db'
if not os.path.exists(db_path):
    print('DB not found:', db_path)
    sys.exit(1)
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('PRAGMA integrity_check;')
result = cur.fetchone()
print('Integrity check result:', result[0])
conn.close()

