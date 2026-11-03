"""Thread‑safe performance data collector.
All records are written to ``scratch/perf_records.json`` which is listed in
``.gitignore`` so they never become part of the repository.
Each request gets a unique UUID; only timing numbers are stored – no prompt
text or user data.
"""

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Dict

# -------------------------------------------------------------------------
# Global lock protecting the in‑memory dict and the on‑disk file.
# -------------------------------------------------------------------------
_lock = threading.Lock()
_file_path = Path(__file__).with_name("perf_records.json")

# In‑memory store mirroring the JSON file.
perf_data: Dict[str, Dict[str, Any]] = {}

def _load() -> None:
    """Load existing records from disk (if any)."""
    if _file_path.is_file():
        try:
            with _file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    perf_data.update(data)
        except Exception:
            # Corrupt file – ignore and start fresh.
            pass

def _save() -> None:
    """Persist ``perf_data`` to disk atomically."""
    with _lock:
        try:
            _file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = _file_path.with_suffix('.tmp')
            with tmp_path.open('w', encoding='utf-8') as f:
                json.dump(perf_data, f, indent=2, sort_keys=True)
            tmp_path.replace(_file_path)
        except Exception:
            pass

# Load any existing records on import.
_load()

def new_request_id() -> str:
    """Generate a fresh UUID for a new request."""
    return str(uuid.uuid4())

def record(request_id: str, metric: str, value: Any) -> None:
    """Record a metric for ``request_id`` and immediately persist.

    This function is thread‑safe.
    """
    with _lock:
        perf_data.setdefault(request_id, {})[metric] = value
        _save()

def dump_perf_report(report_path: Path) -> None:
    """Write a snapshot of the current data to ``report_path`` (used by the
    reporting script)."""
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open('w', encoding='utf-8') as f:
            json.dump(perf_data, f, indent=2, sort_keys=True)
    except Exception:
        pass

