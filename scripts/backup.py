#!/usr/bin/env python3
"""Download a JSON backup of your OMNI data from a running server (stdlib only).

Usage:  OMNI_URL=https://your-omni.example OMNI_ACCESS_TOKEN=... python scripts/backup.py [outfile]
Restore: Memory tab -> "Restore backup…" (replaces current data after confirmation).
The backup contains conversations, memories and notes — not keys, tokens or settings. Keep it private.
"""
import datetime
import json
import os
import sys
import urllib.request

url = os.environ.get("OMNI_URL", "http://127.0.0.1:8000").rstrip("/")
token = os.environ.get("OMNI_ACCESS_TOKEN", "")
req = urllib.request.Request(url + "/api/export", headers={"Authorization": f"Bearer {token}"} if token else {})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
except Exception as e:  # noqa: BLE001 - report any failure plainly
    sys.exit(f"Backup failed: {e}")
out = sys.argv[1] if len(sys.argv) > 1 else f"omni-backup-{datetime.date.today()}.json"
with open(out, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
os.chmod(out, 0o600)
print(f"Saved {out}: {len(data['conversations'])} conversations, {len(data['memories'])} memories, {len(data['notes'])} notes")
