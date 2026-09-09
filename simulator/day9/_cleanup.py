"""Clean up malicious test rows + check ID sequence."""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from db import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

print("=== All mappings before cleanup ===")
rows = conn.execute("SELECT * FROM device_mappings ORDER BY id").fetchall()
for r in rows:
    malicious = "DROP" in r["gateway_key"].upper() or ";" in r["gateway_key"]
    flag = "⚠️ MALICIOUS" if malicious else ""
    print(f"  [{r['id']}] {r['gateway_key']:30s} → {r['product_id']:12s}/{r['device_id']:10s} enabled={r['enabled']} {flag}")

# Delete malicious rows
bad_ids = [r["id"] for r in rows if "DROP" in r["gateway_key"].upper() or ";" in r["gateway_key"]]
if bad_ids:
    print(f"\nDeleting malicious rows: {bad_ids}")
    conn.executemany("DELETE FROM device_mappings WHERE id=?", [(i,) for i in bad_ids])
    conn.commit()

# Check ID autoincrement
seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='device_mappings'").fetchone()
print(f"\nAutoincrement seq: {seq}")

# Reset seq if needed
good_rows = conn.execute("SELECT MAX(id) FROM device_mappings").fetchone()[0]
print(f"Max good ID: {good_rows}")
if good_rows and seq and seq[0] > good_rows + 1:
    conn.execute("UPDATE sqlite_sequence SET seq=?", (good_rows,))
    conn.commit()
    print(f"Reset seq to {good_rows}")

print("\n=== After cleanup ===")
for r in conn.execute("SELECT * FROM device_mappings ORDER BY id").fetchall():
    print(f"  [{r['id']}] {r['gateway_key']:15s} → {r['product_id']:12s}/{r['device_id']:10s} enabled={r['enabled']}")

conn.close()
