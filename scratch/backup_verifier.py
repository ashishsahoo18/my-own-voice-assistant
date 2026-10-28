"""Create and verify timestamped backup of all user data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = ROOT / "backups" / f"v1_baseline_{TIMESTAMP}"

FILES_TO_BACKUP = [
    "database/ayra_chat.db",
    "database/ayra_memory.db",
    "database/memory.db",
    "contacts.csv",
    "config/voice_settings.json",
    ".env",
    ".env.example",
]


def sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "timestamp": TIMESTAMP,
        "backup_dir": str(BACKUP_DIR),
        "files": {},
        "verified": True,
    }

    print(f"Starting backup into {BACKUP_DIR}...")

    for rel_path_str in FILES_TO_BACKUP:
        src = ROOT / rel_path_str
        if not src.exists():
            print(f"Skipping missing file: {rel_path_str}")
            continue

        dest = BACKUP_DIR / rel_path_str
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

        # Make backup file read-only on Windows
        os.chmod(dest, 0o444)

        src_hash = sha256_of_file(src)
        dest_hash = sha256_of_file(dest)

        matches = src_hash == dest_hash
        if not matches:
            manifest["verified"] = False

        manifest["files"][rel_path_str] = {
            "source": str(src),
            "dest": str(dest),
            "source_sha256": src_hash,
            "dest_sha256": dest_hash,
            "match": matches,
            "size_bytes": src.stat().st_size,
        }
        print(f"[{'OK' if matches else 'FAIL'}] {rel_path_str} -> {dest_hash[:12]}... (matches: {matches})")

    manifest_file = BACKUP_DIR / "backup_manifest.json"
    with manifest_file.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    if not manifest["verified"]:
        raise RuntimeError("Backup verification failed: SHA-256 hash mismatch!")

    print(f"\nBackup complete and verified: {manifest_file}")


if __name__ == "__main__":
    main()
