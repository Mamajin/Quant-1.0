"""Maintenance task implementations, separated from the CLI so they're
testable without shelling out or touching the real database (manual sec 4.3
'Vacuum/compact DuckDB', sec 4.10 'scan dependencies for vulnerabilities
(pip-audit)')."""
from __future__ import annotations

import subprocess
import sys

import duckdb

from ..config import StorageConfig


def vacuum_database(con: duckdb.DuckDBPyConnection) -> None:
    """Reclaim space and flush the write-ahead log to the main database
    file (sec 4.3). Safe to run on a live single-user connection."""
    con.execute("VACUUM")
    con.execute("CHECKPOINT")


def database_size_bytes(storage: StorageConfig) -> int:
    """On-disk size of the DuckDB file, for the sec 4.3 storage-math sanity
    checks -- 0 if it doesn't exist yet (fresh install)."""
    db_path = storage.resolved_db_path()
    return db_path.stat().st_size if db_path.exists() else 0


def run_pip_audit(extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """sec 4.10: 'scan dependencies for vulnerabilities (pip-audit)'. Runs
    against this project's own environment (`uv.lock`'s resolved packages,
    since pip-audit inspects what's actually installed)."""
    cmd = [sys.executable, "-m", "pip_audit"] + (extra_args or [])
    return subprocess.run(cmd, check=False, capture_output=True, text=True)
